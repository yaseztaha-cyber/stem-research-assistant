from typing import List, Dict

def assess_evidence_sufficiency(query: str, query_type: str, retrieved: List[Dict], required_concepts: List[str] = None, required_values: List[str] = None) -> Dict:
    """
    Assess whether retrieved evidence is sufficient to answer query.
    States: sufficient, partially_sufficient, insufficient, conflicting
    """
    if not retrieved:
        return {"status": "insufficient", "reason": "No evidence retrieved", "coverage": 0}

    # Check for conflicting evidence (inline to avoid circular import)
    conflict = {"has_conflict": False, "conflicts": []}
    try:
        import re
        eff_sources = []
        for r in retrieved:
            for m in re.finditer(r"(\d+\.?\d*)\s*%\s*(?:efficiency)?|efficiency\s*[=:]\s*(\d+\.?\d*)\s*%", r["text"], re.IGNORECASE):
                val = m.group(1) or m.group(2)
                if val:
                    try:
                        eff_sources.append((float(val), r["document_name"], r["page_number"]))
                    except: pass
        if len(set([v for v,_,_ in eff_sources]))>1:
            vals = [v for v,_,_ in eff_sources]
            if max(vals)-min(vals) > 2:
                conflict = {"has_conflict": True, "conflicts": [{"metric":"efficiency","values":eff_sources}]}
    except Exception:
        pass
    if conflict.get("has_conflict"):
        # If conflict and query is not about comparing, then evidence is conflicting
        if query_type not in ("comparison", "contradiction"):
            return {"status": "conflicting", "reason": "Conflicting values across sources", "conflicts": conflict["conflicts"], "coverage": 0.5}

    # Check required concepts coverage
    required_concepts = required_concepts or []
    required_values = required_values or []
    text_combined = " ".join([r["text"].lower() for r in retrieved])
    concepts_found = sum(1 for c in required_concepts if c.lower() in text_combined)
    values_found = sum(1 for v in required_values if v.lower() in text_combined)

    total_required = len(required_concepts) + len(required_values)
    if total_required == 0:
        # Use query_type heuristic
        # For factual queries, need at least 1 chunk with high relevance
        avg_score = sum(r.get("retrieval_score",0) for r in retrieved[:3])/3 if retrieved else 0
        if avg_score > 0.4 and len(retrieved)>=2:
            return {"status": "sufficient", "reason": "High relevance evidence found", "coverage": 0.9}
        elif avg_score > 0.2:
            return {"status": "partially_sufficient", "reason": "Some relevant evidence", "coverage": 0.6}
        else:
            return {"status": "insufficient", "reason": "Low relevance", "coverage": 0.3}

    found = concepts_found + values_found
    coverage = found / max(total_required,1)
    if coverage >= 0.8:
        status = "sufficient"
    elif coverage >= 0.5:
        status = "partially_sufficient"
    elif coverage > 0:
        status = "partially_sufficient"
    else:
        status = "insufficient"

    return {
        "status": status,
        "reason": f"Found {found}/{total_required} required elements",
        "concepts_found": concepts_found,
        "values_found": values_found,
        "coverage": round(coverage,3),
        "required_concepts": required_concepts,
        "required_values": required_values
    }
