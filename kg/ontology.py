"""Medical ontology for KG relations.

Normalizes LLM-generated predicates to canonical uppercase forms
to prevent graph dilution from synonyms.
"""

from __future__ import annotations

# Canonical predicate ontology
# Map các biến thể về dạng chuẩn
canonical_predicates: dict[str, str] = {
    # Treatment relations
    "treats": "TREATS",
    "treat": "TREATS",
    "treatment_for": "TREATS",
    "used_for": "TREATS",
    "used_to_treat": "TREATS",
    "indicated_for": "TREATS",
    "therapy_for": "TREATS",
    "cures": "TREATS",
    "heals": "TREATS",
    "medicine_for": "TREATS",
    "thuốc điều trị": "TREATS",
    "điều trị": "TREATS",
    "chữa": "TREATS",
    "trị": "TREATS",
    
    # Causal relations
    "causes": "CAUSES",
    "cause": "CAUSES",
    "caused_by": "CAUSED_BY",
    "gây ra": "CAUSES",
    "gây": "CAUSES",
    "nguyên nhân": "CAUSES",
    "lead_to": "CAUSES",
    "results_in": "CAUSES",
    
    # Symptom relations
    "has_symptom": "HAS_SYMPTOM",
    "symptom_of": "SYMPTOM_OF",
    "presents_with": "HAS_SYMPTOM",
    "manifests_as": "HAS_SYMPTOM",
    "triệu chứng": "HAS_SYMPTOM",
    "biểu hiện": "HAS_SYMPTOM",
    
    # Indication/Diagnosis
    "indicates": "INDICATES",
    "indication": "INDICATES",
    "diagnoses": "INDICATES",
    "diagnosis": "INDICATES",
    "chẩn đoán": "INDICATES",
    "dấu hiệu": "INDICATES",
    
    # Contraindications
    "contraindicated_for": "CONTRAINDICATED_FOR",
    "contraindication": "CONTRAINDICATED_FOR",
    "avoid_in": "CONTRAINDICATED_FOR",
    "chống chỉ định": "CONTRAINDICATED_FOR",
    "không dùng cho": "CONTRAINDICATED_FOR",
    
    # Interactions
    "interacts_with": "INTERACTS_WITH",
    "interaction": "INTERACTS_WITH",
    "tương tác": "INTERACTS_WITH",
    "phản ứng với": "INTERACTS_WITH",
    "combine_with": "INTERACTS_WITH",
    
    # Side effects
    "side_effect_of": "SIDE_EFFECT_OF",
    "side_effect": "SIDE_EFFECT_OF",
    "adverse_effect": "SIDE_EFFECT_OF",
    "tác dụng phụ": "SIDE_EFFECT_OF",
    "phản ứng phụ": "SIDE_EFFECT_OF",
    
    # Anatomy/Location
    "located_in": "LOCATED_IN",
    "part_of": "PART_OF",
    "found_in": "LOCATED_IN",
    "nằm ở": "LOCATED_IN",
    "thuộc": "PART_OF",
    "bộ phận của": "PART_OF",
    
    # Test/Procedure
    "detects": "DETECTS",
    "measures": "MEASURES",
    "evaluates": "EVALUATES",
    "used_to_diagnose": "DETECTS",
    "xét nghiệm": "DETECTS",
    "đo": "MEASURES",
    
    # Risk factors
    "risk_factor_for": "RISK_FACTOR_FOR",
    "predisposes_to": "RISK_FACTOR_FOR",
    "yếu tố nguy cơ": "RISK_FACTOR_FOR",
    
    # Prevention
    "prevents": "PREVENTS",
    "prevention": "PREVENTS",
    "protects_against": "PREVENTS",
    "phòng ngừa": "PREVENTS",
    "ngăn ngừa": "PREVENTS",
}


def normalize_predicate(raw: str | None) -> str:
    """Normalize a raw predicate to canonical form.
    
    Args:
        raw: Raw predicate from LLM extraction
        
    Returns:
        Canonical uppercase predicate or "RELATED_TO" if unknown
        
    Examples:
        >>> normalize_predicate("treats")
        "TREATS"
        >>> normalize_predicate("used to treat")
        "TREATS"
        >>> normalize_predicate("gây ra")
        "CAUSES"
        >>> normalize_predicate("random_relation")
        "RELATED_TO"
    """
    if not raw:
        return "RELATED_TO"
    
    # Normalize input
    key = raw.strip().lower().replace("_", " ").replace("-", " ")
    
    # Try direct lookup
    if key in canonical_predicates:
        return canonical_predicates[key]
    
    # Try with spaces normalized
    key = " ".join(key.split())
    if key in canonical_predicates:
        return canonical_predicates[key]
    
    # Return as-is if already uppercase and known
    upper = raw.strip().upper()
    if upper in {v for v in canonical_predicates.values()}:
        return upper
    
    # Unknown predicate - return generic
    return "RELATED_TO"


def get_predicate_ontology() -> list[str]:
    """Get list of all canonical predicates."""
    return sorted(set(canonical_predicates.values()))


def is_medical_predicate(predicate: str) -> bool:
    """Check if a predicate is a known medical relation."""
    return normalize_predicate(predicate) != "RELATED_TO"
