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
            all_results.append((result.text, result.sources))
        # Merge and deduplicate
        seen_sources = set()
        merged_texts = []
        merged_hits = []
        for text, sources in all_results:
            for src in sources:
                src_key = (src.get("title", ""), src.get("source", ""))
                if src_key not in seen_sources:
                    seen_sources.add(src_key)
                    merged_hits.append(src)
            if text.strip():
                merged_texts.append(text)
        return "\n\n".join(merged_texts), merged_hits

    if not oq:
        result = repo.query(ai)
        return result.text, result.sources

    if not ai or ai.casefold() == oq.casefold():
        result = repo.query(oq)
        return result.text, result.sources

    # Check if one contains the other
    oql, ail = oq.casefold(), ai.casefold()
    if oql in ail or ail in oql:
        result = repo.query(oq)
        return result.text, result.sources

    # Merge both for better retrieval
    result = repo.query(oq, retrieval_query=f"{oq} {ai}".strip())
    return result.text, result.sources


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
