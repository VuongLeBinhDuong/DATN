"""Tool execution for ReAct agent.

Provides unified interface for:
- graphrag_query: Knowledge graph retrieval (via Repository pattern)
- pill_image_lookup: Drug image search
"""

from __future__ import annotations

from typing import Any

from agent.tools import (
    expand_query_with_llm,
    merge_retrieval_hits,
    pill_image_lookup_with_urls,
    try_auto_pill_images_for_question,
)
from repositories import get_knowledge_repository

# Repository instance (lazy-loaded)
_repo = None


def _get_repo():
    """Get or create knowledge repository singleton."""
    global _repo
    if _repo is None:
        _repo = get_knowledge_repository("auto")
    return _repo


def set_repository(repo) -> None:
    """Override default repository (useful for testing)."""
    global _repo
    _repo = repo


class ToolObservationStr(str):
    """Custom string subclass to attach raw context metadata to observations."""
    def __new__(cls, value: str, raw_context: str | None = None) -> ToolObservationStr:
        obj = super().__new__(cls, value)
        obj.raw_context = raw_context if raw_context is not None else value
        return obj


def run_graphrag_tool(
    action_input: str | None,
    original_question: str,
    use_expansion: bool = True,
) -> tuple[str, list[dict[str, Any]]]:
    """Execute graphrag_query tool with merged query strategy.
    
    Uses Repository pattern to abstract Neo4j/CLI backend.
    Combines original question with action input for better retrieval.
    
    Args:
        action_input: The specific search terms from ReAct
        original_question: The full user question for context
        use_expansion: Enable query expansion for short queries
        
    Returns:
        Tuple of (observation_text, retrieval_hits)
    """
    oq = (original_question or "").strip()
    ai = (action_input or "").strip()
    
    repo = _get_repo()
    
    # Query Expansion: expand short queries for better retrieval
    if use_expansion and len(oq.split()) <= 10:
        variations = expand_query_with_llm(oq, num_variations=3)
        all_results = []
        for var in variations:
            result = repo.query(var)
            raw_ctx = None
            if isinstance(result.metadata, dict):
                raw_ctx = result.metadata.get("raw_context")
            all_results.append((result.text, result.sources, raw_ctx))
        # Merge and deduplicate
        seen_sources = set()
        merged_texts = []
        merged_hits = []
        merged_raw_contexts = []
        for text, sources, raw_ctx in all_results:
            for src in sources:
                src_key = (src.get("title", ""), src.get("source", ""))
                if src_key not in seen_sources:
                    seen_sources.add(src_key)
                    merged_hits.append(src)
            if text.strip():
                merged_texts.append(text)
            if isinstance(raw_ctx, str) and raw_ctx.strip():
                merged_raw_contexts.append(raw_ctx)
        return ToolObservationStr("\n\n".join(merged_texts), "\n\n".join(merged_raw_contexts)), merged_hits

    if not oq:
        result = repo.query(ai)
        raw_ctx = result.metadata.get("raw_context") if isinstance(result.metadata, dict) else None
        return ToolObservationStr(result.text, raw_ctx), result.sources

    if not ai or ai.casefold() == oq.casefold():
        result = repo.query(oq)
        raw_ctx = result.metadata.get("raw_context") if isinstance(result.metadata, dict) else None
        return ToolObservationStr(result.text, raw_ctx), result.sources

    # Check if one contains the other
    oql, ail = oq.casefold(), ai.casefold()
    if oql in ail or ail in oql:
        result = repo.query(oq)
        raw_ctx = result.metadata.get("raw_context") if isinstance(result.metadata, dict) else None
        return ToolObservationStr(result.text, raw_ctx), result.sources

    # Merge both for better retrieval
    result = repo.query(oq, retrieval_query=f"{oq} {ai}".strip())
    raw_ctx = result.metadata.get("raw_context") if isinstance(result.metadata, dict) else None
    return ToolObservationStr(result.text, raw_ctx), result.sources


def run_pill_image_tool(action_input: str | None) -> tuple[str, list[str]]:
    """Execute pill_image_lookup tool.
    
    Args:
        action_input: Drug name or keyword to search
        
    Returns:
        Tuple of (observation_text, image_urls)
    """
    return pill_image_lookup_with_urls(action_input or "")


def merge_pill_observation(
    question: str,
    base_observation: str,
    current_image_urls: list[str],
) -> tuple[str, list[str]]:
    """Merge auto-detected pill images into observation.
    
    Args:
        question: User question for drug name detection
        base_observation: Base text from graphrag
        current_image_urls: Currently accumulated image URLs
        
    Returns:
        Tuple of (merged_observation, updated_image_urls)
    """
    extra, new_urls = try_auto_pill_images_for_question(question)

    # Filter out already-seen URLs
    filtered_urls = [u for u in new_urls if u and u not in current_image_urls]

    if not filtered_urls:
        return base_observation, current_image_urls

    # Update accumulated URLs
    updated_urls = current_image_urls + filtered_urls

    if not (extra or "").strip():
        return base_observation, updated_urls

    merged = (
        base_observation
        + "\n\n--- Ảnh minh họa (dataset crawl, tham khảo) ---\n"
        + extra
    )
    return merged, updated_urls


def run_medical_calculator_tool(action_input: str | None) -> str:
    """Execute medical_calculator tool.
    
    Computes BMI or Kidney Function (eGFR Cockcroft-Gault) based on inputs.
    Action Input must be a JSON string like:
    {"type": "bmi", "weight": 70, "height": 175}
    or
    {"type": "egfr", "age": 65, "weight": 70, "creatinine": 1.2, "gender": "male"}
    """
    import json
    import re
    
    inp = (action_input or "").strip()
    if not inp:
        return "Error: Action Input is empty. Please provide a JSON input."
        
    try:
        # Clean JSON string (remove markdown block wrapper if present)
        if inp.startswith("```"):
            inp = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", inp)
            inp = re.sub(r"\s*```$", "", inp).strip()
            
        data = json.loads(inp)
    except Exception as e:
        return f"Error parsing JSON input: {e}. Example format: {{\"type\": \"bmi\", \"weight\": 70, \"height\": 175}}"
        
    calc_type = str(data.get("type") or "").lower()
    if calc_type == "bmi":
        weight = data.get("weight")
        height = data.get("height")
        if not weight or not height:
            return "Error: Please provide both 'weight' (kg) and 'height' (cm)."
        try:
            w = float(weight)
            h = float(height) / 100.0  # convert to meters
            bmi = w / (h * h)
            
            # Classification based on WHO criteria
            if bmi < 18.5:
                status = "Gầy (Cân nặng thấp)"
            elif bmi < 25.0:
                status = "Bình thường (Cân nặng lý tưởng)"
            elif bmi < 30.0:
                status = "Tiền béo phì"
            else:
                status = "Béo phì"
                
            return f"Kết quả tính BMI: {bmi:.1f} kg/m² - Trạng thái: {status}."
        except Exception as e:
            return f"Error calculating BMI: {e}"
            
    elif calc_type == "egfr":
        age = data.get("age")
        weight = data.get("weight")
        creatinine = data.get("creatinine")
        gender = str(data.get("gender") or "").lower()
        
        if not all([age, weight, creatinine, gender]):
            return "Error: Please provide 'age', 'weight' (kg), 'creatinine' (mg/dL), and 'gender' ('male' or 'female')."
            
        try:
            a = float(age)
            w = float(weight)
            cr = float(creatinine)
            
            # Normalise gender input for Vietnamese and English
            g_lower = gender.strip().lower()
            if g_lower in ("male", "nam", "m"):
                is_female = False
            elif g_lower in ("female", "nữ", "nu", "f"):
                is_female = True
            else:
                return f"Error: Invalid 'gender' value '{gender}'. Must be 'male' or 'female'."
                
            # Cockcroft-Gault Formula
            egfr = ((140 - a) * w) / (72 * cr)
            if is_female:
                egfr *= 0.85
                
            # eGFR Classification (Kidney function)
            if egfr >= 90:
                status = "Giai đoạn 1: Chức năng lọc thận bình thường hoặc tăng cao"
            elif egfr >= 60:
                status = "Giai đoạn 2: Suy giảm chức năng lọc thận mức độ nhẹ"
            elif egfr >= 30:
                status = "Giai đoạn 3: Suy giảm chức năng lọc thận mức độ trung bình"
            elif egfr >= 15:
                status = "Giai đoạn 4: Suy giảm chức năng lọc thận mức độ nặng"
            else:
                status = "Giai đoạn 5: Suy thận mạn giai đoạn cuối (Cần tham khảo bác sĩ chuyên khoa lọc máu)"
                
            return f"Kết quả tính eGFR (Cockcroft-Gault): {egfr:.1f} mL/min - Phân loại chức năng thận: {status}."
        except Exception as e:
            return f"Error calculating eGFR: {e}"
            
    else:
        return f"Error: Unknown calculator type '{calc_type}'. Supported types: 'bmi', 'egfr'."


def run_drug_interaction_checker_tool(action_input: str | None) -> str:
    """Check drug-drug interactions in the Neo4j Knowledge Graph.
    
    Action Input must be a JSON string like:
    {"drugs": ["metformin", "aspirin"]}
    """
    import json
    import re
    from kg.neo4j_client import Neo4jKGClient
    
    inp = (action_input or "").strip()
    if not inp:
        return "Error: Action Input is empty. Please provide a JSON input."
        
    try:
        if inp.startswith("```"):
            inp = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", inp)
            inp = re.sub(r"\s*```$", "", inp).strip()
            
        data = json.loads(inp)
    except Exception as e:
        drugs = re.findall(r"\b[A-Za-z0-9\-\+]{3,30}\b", inp)
        stop_words = {"and", "with", "or", "drug", "interaction", "check", "vs", "versus"}
        drugs = [d for d in drugs if d.lower() not in stop_words]
        data = {"drugs": drugs}

    drugs = data.get("drugs")
    if not drugs or not isinstance(drugs, list) or len(drugs) < 2:
        return "Error: Please provide at least two drug names in the list. Example: {\"drugs\": [\"metformin\", \"aspirin\"]}"

    try:
        client = Neo4jKGClient()
        resolved_entities = []
        resolved_ids = []
        
        for drug in drugs:
            drug = drug.strip()
            matched = client.search_entities_fulltext(drug, limit=1)
            if matched and matched[0].get("entity_id"):
                resolved_entities.append(matched[0])
                resolved_ids.append(matched[0]["entity_id"])
            else:
                resolved_entities.append({"entity_id": drug, "canonical_name": drug, "type": "DRUG"})
                resolved_ids.append(drug)
                
        subgraph = client.find_paths_between_entities(resolved_ids, max_hops=2)
        edges = subgraph.get("edges") or []
        entities_map = {e["entity_id"]: e for e in subgraph.get("entities") or []}
        
        if not edges:
            driver, db = client._connection()
            cypher = (
                "MATCH (c:Chunk)-[:MENTIONS]->(e1:Entity) "
                "MATCH (c)-[:MENTIONS]->(e2:Entity) "
                "WHERE e1.entity_id IN $ids AND e2.entity_id IN $ids AND e1.entity_id < e2.entity_id "
                "RETURN e1.canonical_name AS drug_a, e2.canonical_name AS drug_b, "
                "       c.text AS text "
                "LIMIT 3"
            )
            with driver.session(database=db) as session:
                co_occurrences = [dict(r) for r in session.run(cypher, {"ids": resolved_ids})]
                
            if co_occurrences:
                report = ["### Phát hiện đồng xuất hiện trong tài liệu y tế (Không có mối quan hệ trực tiếp trong đồ thị):\n"]
                for item in co_occurrences:
                    report.append(f"- **{item['drug_a']}** và **{item['drug_b']}** được đề cập cùng nhau trong ngữ cảnh:")
                    snippet = item['text']
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
                    report.append(f"  > \"{snippet}\"\n")
                return "\n".join(report)
                
            return f"Không tìm thấy dữ liệu tương tác hoặc đồng xuất hiện trực tiếp nào giữa các thuốc [{', '.join(drugs)}] trong cơ sở dữ liệu đồ thị tri thức Neo4j."

        report = [f"### KẾT QUẢ TRA CỨU TƯƠNG TÁC THUỐC (NEO4J - GRAPH TRAVERSAL):\n"]
        
        evidence_ids = [edge["evidence_chunk_id"] for edge in edges if edge.get("evidence_chunk_id")]
        chunks = client.fetch_chunks_by_ids(evidence_ids) if evidence_ids else []
        chunks_map = {c["chunk_id"]: c for c in chunks}
        
        for idx, edge in enumerate(edges):
            pred = edge["predicate"]
            sub_id = edge["subject_entity_id"]
            obj_id = edge["object_entity_id"]
            conf = edge["confidence"]
            evidence_id = edge.get("evidence_chunk_id")
            
            sub_name = entities_map.get(sub_id, {}).get("canonical_name", sub_id)
            obj_name = entities_map.get(obj_id, {}).get("canonical_name", obj_id)
            
            pred_vn = {
                "INTERACTS_WITH": "Tương tác với",
                "CONTRAINDICATED_FOR": "Chống chỉ định cho",
                "SIDE_EFFECT_OF": "Tác dụng phụ của",
                "TREATS": "Điều trị",
                "CAUSES": "Gây ra",
                "HAS_SYMPTOM": "Có triệu chứng"
            }.get(pred, pred)
            
            report.append(f"{idx+1}. **{sub_name}** -- [{pred_vn} (độ tin cậy: {conf:.2f})] --> **{obj_name}**")
            
            if evidence_id and evidence_id in chunks_map:
                evidence_text = chunks_map[evidence_id]["text"]
                if len(evidence_text) > 400:
                    evidence_text = evidence_text[:400] + "..."
                report.append(f"   * Bằng chứng lâm sàng:* \"{evidence_text}\"\n")
            else:
                report.append("   * Bằng chứng lâm sàng:* (Không có văn bản trích dẫn cụ thể)\n")
                
        return "\n".join(report)
        
    except Exception as e:
        return f"Error executing drug interaction checker: {e}"
