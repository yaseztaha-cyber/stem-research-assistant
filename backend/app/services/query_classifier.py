import re
from typing import Dict

# Lightweight rule-based classifier, no LLM needed

PATTERNS = {
    "equation": [
        r"equation", r"formula", r"P\s*=\s*VI", r"V\s*=\s*IR", r"V\s*=\s*S", r"defines", r"law",
        r"what.*equation", r"variable", r"unit"
    ],
    "experimental_result": [
        r"result", r"experimental", r"measured", r"output", r"improvement", r"increase",
        r"reported", r"\d+\s*%", r"efficiency", r"power", r"W", r"ZT"
    ],
    "definition": [
        r"what is", r"define", r"definition", r"meaning", r"explain.*concept", r"what is the seebeck"
    ],
    "concept": [
        r"explain", r"mechanism", r"how does", r"why", r"intuition", r"describe"
    ],
    "calculation": [
        r"calculate", r"compute", r"solve", r"how much", r"given.*find", r"determine", r"if.*doubles", r"what happens.*if", r"how much.*if", r"calculate.*power", r"calculate.*q"
    ],
    "methodology": [
        r"method", r"procedure", r"setup", r"experimental setup", r"how was.*done", r"steps"
    ],
    "comparison": [
        r"compare", r"difference between", r"versus", r"vs\.", r"contrast", r"which.*better", r"paper a.*paper b"
    ],
    "dataset": [
        r"dataset", r"csv", r"correlation", r"distribution", r"statistics", r"missing values", r"anomal"
    ],
    "procedure": [
        r"procedure", r"lab manual", r"steps", r"materials", r"safety", r"protocol"
    ],
    "citation": [
        r"cite", r"citation", r"reference", r"apa", r"ieee", r"mla", r"doi"
    ],
    "table": [
        r"table", r"which.*configuration", r"highest.*power", r"lowest", r"row", r"value at", r"DeltaT.*power", r"which.*delta", r"power.*\d+"
    ],
}

def classify_query(query: str) -> Dict:
    q_low = query.lower()
    # Hard rule: calculate prioritizes calculation
    if re.search(r"\bcalculate\b", q_low) or re.search(r"\bcompute\b", q_low):
        scores = {k:0 for k in PATTERNS}
        scores["calculation"] = 5
        # also check secondary
        secondary = []
        for qtype, patterns in PATTERNS.items():
            if qtype=="calculation": continue
            for pat in patterns:
                if re.search(pat, q_low):
                    secondary.append(qtype)
                    break
        return {
            "query_type": "calculation",
            "confidence": 0.9,
            "scores": scores,
            "secondary_types": list(set(secondary))[:2],
            "is_equation": False,
            "is_comparison": False,
            "is_experimental": False,
        }
    # Hard rule: derived/calculation for what happens if
    if re.search(r"what happens.*if", q_low) or re.search(r"if.*doubles", q_low):
        scores = {k:0 for k in PATTERNS}
        scores["calculation"] = 5
        return {
            "query_type": "calculation",
            "confidence": 0.85,
            "scores": scores,
            "secondary_types": [],
            "is_equation": False,
            "is_comparison": False,
            "is_experimental": False,
        }
    # Hard rule: table queries
    if re.search(r"\bwhich\b.*\b(configuration|highest|lowest|value|row|table)\b", q_low) or ("table" in q_low and "power" in q_low):
        scores = {k:0 for k in PATTERNS}
        scores["table"] = 5
        # Check if also equation?
        return {
            "query_type": "table",
            "confidence": 0.85,
            "scores": scores,
            "secondary_types": [],
            "is_equation": False,
            "is_comparison": False,
            "is_experimental": False,
        }
    # Hard rule: explicit compare prioritizes comparison
    if re.search(r"\bcompare\b", q_low):
        scores = {k:0 for k in PATTERNS}
        scores["comparison"] = 5
        best = "comparison"
        confidence = 0.9
        secondary = []
        # still compute secondary for info
        for qtype, patterns in PATTERNS.items():
            if qtype=="comparison": continue
            for pat in patterns:
                if re.search(pat, q_low):
                    secondary.append(qtype)
                    break
        return {
            "query_type": best,
            "confidence": confidence,
            "scores": scores,
            "secondary_types": list(set(secondary))[:2],
            "is_equation": False,
            "is_comparison": True,
            "is_experimental": False,
        }

    scores = {}
    for qtype, patterns in PATTERNS.items():
        score = 0
        for pat in patterns:
            if re.search(pat, q_low):
                # weight comparison patterns slightly higher
                weight = 1.5 if qtype=="comparison" and "compare" in pat else 1
                score += weight
        scores[qtype] = score

    # Determine top type
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        best = "general"
        confidence = 0.3
    else:
        # confidence based on how many patterns matched vs second best
        sorted_scores = sorted(scores.values(), reverse=True)
        confidence = 0.6 + 0.1*scores[best] if scores[best]>1 else 0.55
        if len(sorted_scores)>1 and sorted_scores[0]==sorted_scores[1]:
            confidence = 0.45

    # Also detect multi-intent (e.g., equation + comparison)
    secondary = [k for k,v in scores.items() if v>0 and k!=best]

    return {
        "query_type": best,
        "confidence": round(min(confidence, 0.95), 2),
        "scores": scores,
        "secondary_types": secondary[:2],
        "is_equation": best=="equation" or any(t in q_low for t in ["p = vi","v = ir","q = mc","v = s"]),
        "is_comparison": best=="comparison",
        "is_experimental": best=="experimental_result",
    }

def metadata_hint_for_query(query_type: str) -> Dict:
    """Return preferred metadata filters to boost relevant content"""
    hints = {}
    if query_type == "equation":
        hints["content_type"] = "equation"
    elif query_type == "experimental_result":
        hints["content_type"] = "result"
        hints["section"] = "Results"
    elif query_type == "methodology":
        hints["section"] = "Methods"
        hints["content_type"] = "procedure"
    elif query_type == "definition":
        hints["content_type"] = "definition"
    elif query_type == "procedure":
        hints["content_type"] = "procedure"
        hints["section"] = "Procedure"
    elif query_type == "dataset":
        hints["content_type"] = "result"  # dataset overview stored as result-like?
    return hints
