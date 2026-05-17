"""LangChain-based GraphRAG for medical QA (disease/symptom/drug entity graph).

This module queries the Neo4j graph built by the notebook at:
    langchain_graphrag/medical_qa_graph.ipynb

Schema (created by LLMGraphTransformer):
    Nodes: Disease, Symptom, Drug, Treatment, BodyPart, Test, RiskFactor, Cause, Document
    Relationships: HAS_SYMPTOM, TREATED_BY, AFFECTS, DIAGNOSED_BY, HAS_CAUSE, HAS_RISK_FACTOR
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Any

from core.connection_pool import get_neo4j_driver
from llm_pipeline.llm_chat import chat_ollama, synthesis_backend

logger = logging.getLogger(__name__)


def _strip_accents(text: str) -> str:
    """Normalize Vietnamese text to accentless lowercase for robust matching."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    no_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return no_marks.lower()


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _normalize_entity_text(text: str) -> str:
    return _normalize_space((text or "").lower())


def _entity_search_terms(entity_name: str) -> list[str]:
    """Create robust search terms without dropping medically meaningful tokens."""
    clean = _normalize_entity_text(entity_name)
    if not clean:
        return []

    terms: list[str] = [clean]
    compact = clean.replace("-", " ")
    if compact != clean:
        terms.append(compact)

    # Remove generic prefixes only; do not remove words like "cao" from "sot cao".
    for prefix in ("bệnh ", "benh ", "triệu chứng ", "trieu chung ", "thuốc ", "thuoc "):
        if clean.startswith(prefix):
            t = clean[len(prefix) :].strip()
            if t:
                terms.append(t)

    parts = clean.split()
    if len(parts) > 1:
        terms.append(" ".join(parts[:2]))
        terms.append(parts[0])

    # Accentless variants help when graph ids are normalized ASCII.
    accentless = _strip_accents(clean)
    if accentless and accentless != clean:
        terms.append(accentless)

    # Deduplicate while preserving order
    out: list[str] = []
    seen: set[str] = set()
    for t in terms:
        tt = _normalize_space(t)
        if len(tt) >= 2 and tt not in seen:
            seen.add(tt)
            out.append(tt)
    return out

# Entity extraction using simple keyword matching for speed
# (can be upgraded to LLM-based extraction like in the notebook)
MEDICAL_ENTITY_KEYWORDS = {
    # Symptoms (Triệu chứng) - expanded
    "sốt": "Symptom",
    "sốt cao": "Symptom",
    "sốt nhẹ": "Symptom",
    "đau": "Symptom",
    "đau đầu": "Symptom",
    "đau bụng": "Symptom",
    "đau ngực": "Symptom",
    "đau họng": "Symptom",
    "đau lưng": "Symptom",
    "đau răng": "Symptom",
    "ho": "Symptom",
    "ho khan": "Symptom",
    "ho có đờm": "Symptom",
    "mệt mỏi": "Symptom",
    "buồn nôn": "Symptom",
    "nôn": "Symptom",
    "tiêu chảy": "Symptom",
    "táo bón": "Symptom",
    "chóng mặt": "Symptom",
    "khó thở": "Symptom",
    "ngứa": "Symptom",
    "phát ban": "Symptom",
    "mất vị giác": "Symptom",
    "mất khứu giác": "Symptom",
    
    # Diseases (Bệnh) - expanded
    "bệnh": "Disease",
    "viêm": "Disease",
    "cúm": "Disease",
    "cảm": "Disease",
    "cảm cúm": "Disease",
    "covid": "Disease",
    "covid-19": "Disease",
    "nhiễm": "Disease",
    "nhiễm trùng": "Disease",
    "viêm họng": "Disease",
    "viêm phổi": "Disease",
    "viêm gan": "Disease",
    "viêm dạ dày": "Disease",
    "viêm ruột": "Disease",
    "viêm xoang": "Disease",
    "ung thư": "Disease",
    "tiểu đường": "Disease",
    "huyết áp": "Disease",
    "tăng huyết áp": "Disease",
    "gout": "Disease",
    "loãng xương": "Disease",
    "hen suyễn": "Disease",
    
    # Body parts - expanded
    "đầu": "BodyPart",
    "trán": "BodyPart",
    "bụng": "BodyPart",
    "ngực": "BodyPart",
    "cổ": "BodyPart",
    "họng": "BodyPart",
    "tai": "BodyPart",
    "mũi": "BodyPart",
    "mắt": "BodyPart",
    "gan": "BodyPart",
    "thận": "BodyPart",
    "tim": "BodyPart",
    "phổi": "BodyPart",
    "lưng": "BodyPart",
    "răng": "BodyPart",
    "miệng": "BodyPart",
    "dạ dày": "BodyPart",
    "ruột": "BodyPart",
    "xoang": "BodyPart",
    
    # Drugs (Thuốc) - expanded
    "paracetamol": "Drug",
    "aspirin": "Drug",
    "ibuprofen": "Drug",
    "amoxicillin": "Drug",
    "kháng sinh": "Drug",
    "thuốc": "Drug",
    "thuốc hạ sốt": "Drug",
    "thuốc giảm đau": "Drug",
    "thuốc ho": "Drug",
    "thuốc dạ dày": "Drug",
    "men vi sinh": "Drug",
    "or-saline": "Drug",
    
    # Risk factors
    "cao": "RiskFactor",
    "thấp": "RiskFactor",
    "cao tuổi": "RiskFactor",
    "béo phì": "RiskFactor",
    "hút thuốc": "RiskFactor",
    "rượu": "RiskFactor",
    
    # Tests
    "xét nghiệm": "Test",
    "siêu âm": "Test",
    "chụp": "Test",
    "x-quang": "Test",
    "ct": "Test",
    "mri": "Test",
    "máu": "Test",
    "test": "Test",
    "khám": "Test",
}


def _extract_entities_with_llm(question: str, cfg: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Extract medical entities from question using LLM.
    
    Returns list of entities with name and type for querying Neo4j.
    Falls back to empty list if LLM fails.
    """
    cfg = cfg or _get_neo4j_config_from_env()
    host = cfg.get("ollama_host", "http://127.0.0.1:11434")
    model = cfg.get("ollama_model", "llama3.1:8b")
    
    prompt = f"""Từ câu hỏi y tế sau, trích xuất các entity (thực thể) y tế có trong câu hỏi và phân loại chúng.

Câu hỏi: "{question}"

Các loại entity:
- Disease: bệnh, tình trạng bệnh lý (ví dụ: viêm, cúm, tiểu đường, viêm họng, ung thư)
- Symptom: triệu chứng (ví dụ: sốt, đau đầu, ho, buồn nôn, mệt mỏi)
- Drug: thuốc (ví dụ: paracetamol, aspirin, kháng sinh, thuốc hạ sốt)
- BodyPart: bộ phận cơ thể (ví dụ: đầu, bụng, ngực, gan, tim)
- Test: xét nghiệm, chẩn đoán (ví dụ: xét nghiệm máu, siêu âm, x-quang)
- Treatment: phương pháp điều trị (ví dụ: phẫu thuật, vật lý trị liệu, hóa trị)
- RiskFactor: yếu tố nguy cơ (ví dụ: hút thuốc, cao tuổi, béo phì)
- Cause: nguyên nhân (ví dụ: nhiễm trùng, virus, vi khuẩn)

Trả về kết quả dưới dạng JSON array:
[
  {{"name": "tên entity", "type": "Symptom|Disease|Drug|BodyPart|Test|Treatment|RiskFactor|Cause"}}
]

Lưu ý:
- Chỉ trả về JSON array, không giải thích thêm
- Nếu không có entity nào, trả v []
- Tên entity phải chính xác như trong câu hỏi (giữ nguyên tiếng Việt)
- Ưu tiên cụm từ dài hơn (ví dụ: "sốt cao" thay vì chỉ "sốt")"""

    try:
        response = chat_ollama(prompt, host=host, model=model, timeout=30, num_predict=512)
        
        # Try to parse JSON from response
        # LLM might wrap in markdown code blocks, try to extract
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        
        entities = json.loads(text)
        
        # Validate format
        if isinstance(entities, list):
            valid_entities = []
            for e in entities:
                if isinstance(e, dict) and "name" in e:
                    # Normalize type if missing or invalid
                    valid_type = e.get("type", "Disease")
                    if valid_type not in ["Disease", "Symptom", "Drug", "BodyPart", 
                                          "Test", "Treatment", "RiskFactor", "Cause"]:
                        valid_type = "Disease"  # Default fallback
                    valid_entities.append({
                        "name": e["name"],
                        "type": valid_type
                    })
            return valid_entities
        return []
    except Exception as e:
        logger.warning(f"LLM entity extraction failed: {e}")
        return []


def _extract_entities_from_question(question: str, use_llm: bool = True) -> list[dict[str, str]]:
    """Extract medical entities from question.
    
    By default uses LLM for better extraction. Falls back to keyword matching
    if LLM fails or if use_llm=False.
    
    Args:
        question: User's question text
        use_llm: If True, try LLM extraction first
    
    Returns:
        List of entities with name and type
    """
    if use_llm:
        entities = _extract_entities_with_llm(question)
        if entities:
            logger.info(f"LLM extracted entities: {[e['name'] for e in entities]}")
            return entities
        logger.info("LLM extraction returned empty, falling back to keyword matching")
    
    # Fallback: keyword matching
    question_lower = question.lower()
    entities = []
    seen_positions = set()
    
    sorted_keywords = sorted(
        MEDICAL_ENTITY_KEYWORDS.items(),
        key=lambda x: len(x[0]),
        reverse=True
    )
    
    for keyword, entity_type in sorted_keywords:
        if keyword in question_lower:
            start = 0
            while True:
                pos = question_lower.find(keyword, start)
                if pos == -1:
                    break
                
                positions = set(range(pos, pos + len(keyword)))
                if not positions & seen_positions:
                    entities.append({
                        "name": keyword,
                        "type": entity_type,
                    })
                    seen_positions.update(positions)
                
                start = pos + 1
    
    seen_names = set()
    unique_entities = []
    for e in entities:
        if e["name"] not in seen_names:
            unique_entities.append(e)
            seen_names.add(e["name"])
    
    logger.info(f"Keyword extracted entities: {[e['name'] for e in unique_entities]}")
    return unique_entities


def _get_neo4j_config_from_env() -> dict[str, Any]:
    """Get Neo4j config from environment or defaults."""
    return {
        "uri": os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
        "user": os.getenv("NEO4J_USER", "neo4j"),
        "password": os.getenv("NEO4J_PASSWORD", "changeme"),
        "database": os.getenv("NEO4J_DATABASE", "neo4j"),
        "ollama_host": os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
    }


def _query_graph_for_entity(
    session: Any,
    entity_name: str,
    entity_type: str | None = None,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Query graph for a specific entity using fulltext + robust field matching."""
    results = []
    seen_ids = set()
    search_terms = _entity_search_terms(entity_name)

    # Define entity types to search
    entity_types = [
        "Disease",
        "Symptom",
        "Drug",
        "Treatment",
        "BodyPart",
        "Test",
        "RiskFactor",
        "Cause",
    ]
    type_filter = entity_type if entity_type in entity_types else None

    # Try each search term with multiple strategies
    for term in search_terms:
        if not term or len(term) < 2:
            continue

        # Strategy 1: Neo4j fulltext index for medical entities
        try:
            query = """
                CALL db.index.fulltext.queryNodes('graphEntityFulltext', $term)
                YIELD node, score
                WHERE labels(node)[0] IN $types
                  AND ($type_filter IS NULL OR labels(node)[0] = $type_filter)
                RETURN
                  coalesce(node.id, node.title, node.name) as name,
                  labels(node)[0] as type,
                  node as node,
                  score as score
                LIMIT $limit
            """
            records = session.run(query, {
                "term": term,
                "types": entity_types,
                "type_filter": type_filter,
                "limit": max_results
            })
            for r in records:
                name = _normalize_space(str(r.get("name", "")))
                if name and name not in seen_ids:
                    seen_ids.add(name)
                    results.append(dict(r))
        except Exception as e:
            logger.debug(f"Fulltext query failed for '{term}': {e}")

        # Strategy 2: field-aware matching as fallback
        if len(results) < max_results:
            try:
                query = """
                    MATCH (n)
                    WHERE labels(n)[0] IN $types
                      AND ($type_filter IS NULL OR labels(n)[0] = $type_filter)
                      AND (
                        toLower(coalesce(n.id, '')) CONTAINS $term
                        OR toLower(coalesce(n.title, '')) CONTAINS $term
                        OR toLower(coalesce(n.name, '')) CONTAINS $term
                        OR toLower(coalesce(n.description, '')) CONTAINS $term
                      )
                      AND NOT coalesce(n.id, n.title, n.name) IN $seen
                    RETURN
                      coalesce(n.id, n.title, n.name) as name,
                      labels(n)[0] as type,
                      n as node,
                      0.5 as score
                    LIMIT $limit
                """
                records = session.run(query, {
                    "term": term.lower(),
                    "types": entity_types,
                    "type_filter": type_filter,
                    "seen": list(seen_ids),
                    "limit": max_results - len(results)
                })
                for r in records:
                    name = _normalize_space(str(r.get("name", "")))
                    if name and name not in seen_ids:
                        seen_ids.add(name)
                        results.append(dict(r))
            except Exception as e:
                logger.debug(f"Field-match query failed for '{term}': {e}")

        # Strategy 3: accentless fallback for weakly normalized data
        if len(results) < max_results:
            try:
                accentless = _strip_accents(term)
                query = """
                    MATCH (n)
                    WHERE labels(n)[0] IN $types
                      AND ($type_filter IS NULL OR labels(n)[0] = $type_filter)
                      AND (
                        toLower(coalesce(n.id, '')) CONTAINS $term
                        OR toLower(coalesce(n.title, '')) CONTAINS $term
                        OR toLower(coalesce(n.name, '')) CONTAINS $term
                      )
                      AND labels(n)[0] IN $types
                      AND NOT coalesce(n.id, n.title, n.name) IN $seen
                    RETURN
                      coalesce(n.id, n.title, n.name) as name,
                      labels(n)[0] as type,
                      n as node,
                      0.3 as score
                    LIMIT $limit
                """
                records = session.run(query, {
                    "term": accentless,
                    "types": entity_types,
                    "type_filter": type_filter,
                    "seen": list(seen_ids),
                    "limit": max_results - len(results)
                })
                for r in records:
                    name = _normalize_space(str(r.get("name", "")))
                    if name and name not in seen_ids:
                        seen_ids.add(name)
                        results.append(dict(r))
            except Exception as e:
                logger.debug(f"Accentless query failed for '{term}': {e}")

        # If we have enough results, stop
        if len(results) >= max_results:
            break

    return results


def _get_entity_relationships(
    session: Any,
    entity_name: str,
    max_relationships: int = 10,
) -> list[str]:
    """Get relationships for an entity."""
    relationships = []
    relation_types = [
        "HAS_SYMPTOM",
        "TREATED_BY",
        "AFFECTS",
        "DIAGNOSED_BY",
        "HAS_CAUSE",
        "HAS_RISK_FACTOR",
    ]

    try:
        query = """
            MATCH (n)-[r]->(m)
            WHERE type(r) IN $relation_types
              AND (
                toLower(coalesce(n.id, '')) CONTAINS $entity
                OR toLower(coalesce(n.title, '')) CONTAINS $entity
                OR toLower(coalesce(n.name, '')) CONTAINS $entity
              )
            RETURN
              coalesce(n.id, n.title, n.name) as source,
              type(r) as rel,
              coalesce(m.id, m.title, m.name) as target
            LIMIT $limit
        """
        records = session.run(query, {
            "entity": entity_name.lower(),
            "relation_types": relation_types,
            "limit": max_relationships
        })
        for rec in records:
            rel_str = f"{rec['source']} - {rec['rel']} -> {rec['target']}"
            relationships.append(rel_str)
    except Exception as e:
        logger.debug(f"Relationship query failed for '{entity_name}': {e}")

    return relationships


def _get_vector_context(
    session: Any,
    question: str,
    entities: list[dict[str, str]] | None = None,
    max_chunks: int = 3,
) -> list[str]:
    """Get relevant document chunks using fulltext + keyword fallback."""
    chunks = []
    seen_chunks = set()  # Avoid duplicates
    
    # Build list of keywords to search
    keywords = []
    
    # First priority: extracted entity names
    if entities:
        for e in entities:
            entity_name = e.get("name", "")
            if entity_name and len(entity_name) > 1:
                keywords.append(entity_name)
    
    # Fallback: extract important words from question (skip common words)
    skip_words = {
        "toi", "tôi", "ban", "bạn", "co", "có", "la", "là", "gi", "gì",
        "bay", "bây", "gio", "giờ", "can", "cần", "lam", "làm", "thi", "thì",
        "va", "và", "cua", "của", "duoc", "được", "bi", "bị", "cho", "với",
    }
    for word in question.lower().split():
        if len(word) > 2 and word not in skip_words and word not in keywords:
            keywords.append(word)

    try:
        # Search Documents with multiple keywords
        for keyword in keywords[:5]:
            if not keyword or len(keyword) < 2:
                continue

            records = []
            try:
                ft_query = """
                    CALL db.index.fulltext.queryNodes('documentFulltext', $keyword)
                    YIELD node, score
                    WHERE 'Document' IN labels(node)
                    RETURN coalesce(node.text, '') as text, score
                    LIMIT $limit
                """
                records = session.run(ft_query, {"keyword": keyword, "limit": max_chunks})
            except Exception:
                kw_query = """
                    MATCH (d:Document)
                    WHERE toLower(coalesce(d.text, '')) CONTAINS $keyword
                    RETURN coalesce(d.text, '') as text, 0.0 as score
                    LIMIT $limit
                """
                records = session.run(kw_query, {"keyword": keyword.lower(), "limit": max_chunks})

            for rec in records:
                text = (rec.get("text") or "").strip()
                # Skip duplicates based on first 100 chars
                text_key = text[:100]
                if text and text_key not in seen_chunks:
                    seen_chunks.add(text_key)
                    chunks.append(text[:500] + "..." if len(text) > 500 else text)
                    
            if len(chunks) >= max_chunks:
                break
                
    except Exception as e:
        logger.debug(f"Vector context query failed: {e}")

    return chunks[:max_chunks]


def retrieve_langchain_graph_context(
    question: str,
    cfg: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Retrieve context from LangChain-built Neo4j graph.

    Returns:
        Tuple of (context_text, sources_list)
    """
    cfg = cfg or _get_neo4j_config_from_env()

    uri = cfg.get("uri", "bolt://127.0.0.1:7687")
    user = cfg.get("user", "neo4j")
    password = cfg.get("password", "changeme")
    database = cfg.get("database", "neo4j")

    driver = get_neo4j_driver(uri, user, password)
    if driver is None:
        logger.error("Neo4j driver not available")
        return "Neo4j driver not available.", []

    # Extract entities from question
    entities = _extract_entities_from_question(question)
    if not entities:
        # Fallback: try to extract using first few words
        words = question.lower().split()[:3]
        for word in words:
            if len(word) > 2:
                entities.append({"name": word, "type": None})
    
    logger.info(f"Question: '{question}' -> Extracted entities: {entities}")
    
    lines = []
    sources: list[dict[str, Any]] = []
    seen_entities = set()

    try:
        with driver.session(database=database) as session:
            # Query each entity
            for entity in entities:
                entity_results = _query_graph_for_entity(
                    session,
                    entity["name"],
                    entity.get("type"),
                    max_results=3
                )
                
                if entity_results:
                    logger.info(f"Found {len(entity_results)} matches for entity '{entity['name']}'")
                else:
                    logger.info(f"No graph matches for entity '{entity['name']}'")

                for result in entity_results:
                    name = result.get("name", "")
                    if name in seen_entities:
                        continue
                    seen_entities.add(name)

                    entity_type = result.get("type", "Unknown")
                    sources.append({
                        "title": name,
                        "source": f"neo4j:{entity_type}",
                        "score": 1.0,
                    })

                    lines.append(f"--- {entity_type}: {name} ---")

                    # Get relationships for this entity
                    rels = _get_entity_relationships(session, name, max_relationships=5)
                    for rel in rels:
                        lines.append(f"  {rel}")

                    if rels:
                        lines.append("")

            # Get vector context (Document chunks) - pass entities for better search
            doc_chunks = _get_vector_context(session, question, entities=entities, max_chunks=2)
            if doc_chunks:
                lines.append("=== Thông tin từ tài liệu ===")
                for i, chunk in enumerate(doc_chunks, 1):
                    lines.append(f"[{i}] {chunk}")
                    sources.append({
                        "title": f"Document chunk {i}",
                        "source": "neo4j:Document",
                        "score": 0.8,
                    })

    except Exception as e:
        logger.error(f"LangChain graph query failed: {e}")
        return f"Error querying graph: {e}", []

    context = "\n".join(lines).strip()
    if not context:
        return "Không tìm thấy thông tin trong knowledge graph.", []

    return context, sources


def synthesize_langchain_answer(
    question: str,
    graph_context: str,
    cfg: dict[str, Any] | None = None,
) -> str:
    """Synthesize answer using Ollama LLM."""
    cfg = cfg or _get_neo4j_config_from_env()

    host = cfg.get("ollama_host", "http://127.0.0.1:11434")
    model = cfg.get("ollama_model", "llama3.1:8b")

    prompt = f"""Bạn là trợ lý y khoa. Trả lời câu hỏi dựa trên thông tin được cung cấp.

Quy tắc:
1. Chỉ dùng thông tin trong phần "Ngữ cảnh" bên dưới
2. Không suy diễn ngoài dữ liệu
3. Trả lời ngắn gọn, chính xác bằng tiếng Việt
4. Nếu không đủ thông tin, nói rõ "Không có đủ thông tin"

Ngữ cảnh:
{graph_context}

Câu hỏi: {question}

Trả lời:"""

    try:
        if synthesis_backend() == "openrouter":
            # Use default OpenRouter config
            from llm_pipeline.llm_chat import chat_openrouter
            return chat_openrouter(prompt, timeout=60)
        else:
            return chat_ollama(prompt, host=host, model=model, timeout=60, num_predict=1024)
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return f"Lỗi khi tổng hợp câu trả lời: {e}"


def run_langchain_graphrag_query(question: str) -> str:
    """Main entry point: query LangChain graph and synthesize answer."""
    cfg = _get_neo4j_config_from_env()

    context, _ = retrieve_langchain_graph_context(question, cfg)

    if not context or context.startswith("Error") or context.startswith("Không tìm thấy"):
        return context or "Không có thông tin."

    return synthesize_langchain_answer(question, context, cfg)


def run_langchain_graphrag_query_direct(question: str) -> tuple[str, list[dict[str, Any]]]:
    """Query Neo4j directly WITHOUT LLM synthesis - return raw context only.
    
    This is faster and shows the raw data from the knowledge graph.
    Use this when you want to see exactly what's in the database.
    
    Returns:
        Tuple of (raw_context_text, sources_list)
    """
    cfg = _get_neo4j_config_from_env()
    
    context, sources = retrieve_langchain_graph_context(question, cfg)
    
    if not context:
        return "Không tìm thấy thông tin trong knowledge graph.", []
    
    # Add header to indicate this is raw data
    header = f"""=== TRUY VẤN TRỰC TIẾP TỪ NEO4J (KHÔNG QUA LLM) ===
Câu hỏi: {question}
Số nguồn tìm thấy: {len(sources)}

=== NGỮ CẢNH THÔ TỪ GRAPH ===
"""
    
    full_context = header + context
    
    return full_context, sources


def run_langchain_graphrag_query_with_sources(
    question: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Query with source tracking for UI."""
    cfg = _get_neo4j_config_from_env()

    context, sources = retrieve_langchain_graph_context(question, cfg)

    if not context or context.startswith("Error") or context.startswith("Không tìm thấy"):
        return context or "Không có thông tin.", []

    answer = synthesize_langchain_answer(question, context, cfg)
    return answer, sources
