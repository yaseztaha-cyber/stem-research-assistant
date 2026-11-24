"""Answer relevance v3 (v0.5 §28).

v2 is FROZEN (see evaluation_v2_helper.py — do not modify).
v3 exists because human data (n=100, ρ=0.17 for v2 vs human relevance)
demonstrated specific weaknesses:
  1. exact-substring concept matching misses paraphrases AND trivially
     matches boilerplate ("P = VI" appears in conflict footers);
  2. value matching has no numeric tolerance (4.191W vs required 4.2W);
  3. directness rewards any short first sentence, even a wrong one;
  4. pipeline-appended boilerplate (conflict/disclaimer footers) is scored
     as answer content.

v3 fixes these deterministically (no ML, no tuning on the human scores —
fixed tolerance 5%, fixed stemmer, fixed boilerplate list).
Fitted-sample performance is reported WITH the caveat that held-out
validation is still pending.
"""
import re
from typing import List, Dict

# Pipeline-appended boilerplate that is NOT answer content (v0.5 finding:
# the contradiction detector over-triggers, e.g. "power values differ:
# 4.2W, 3.14W" on citation questions). v3 strips these before scoring.
BOILERPLATE_PATTERNS = [
    r"> \*\*Conflict detected.*?(?=\n\n|\Z)",
    r"> ⚠️.*?(?=\n\n|\Z)",
    r"> \*\*Causal claim note.*?(?=\n\n|\Z)",
    r"> Note: Limited evidence.*?(?=\n\n|\Z)",
]

GENERIC_OPENERS = (
    "there are several", "in this", "this paper investigates",
    "it is important", "when it comes to",
)


def strip_boilerplate(answer: str) -> str:
    out = answer
    for pat in BOILERPLATE_PATTERNS:
        out = re.sub(pat, "", out, flags=re.DOTALL | re.IGNORECASE)
    return out.strip()


def _stem(tok: str) -> str:
    """Minimal deterministic stemmer (no new dependencies)."""
    t = tok.lower()
    for suf in ("ization", "isation", "ational", "fulness", "ousness", "iveness",
                "ement", "ments", "ment", "ance", "ence", "able", "ible",
                "ness", "less", "tion", "sion", "ing", "edly", "edly",
                "ied", "ies", "ed", "es", "ly", "s"):
        if len(t) - len(suf) >= 4 and t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t


def _norm_text(s: str) -> str:
    s = s.lower().replace("percent", "%").replace("·", "*")
    s = re.sub(r"\s+", " ", s)
    return s


def _parse_number_unit(s: str):
    m = re.match(r"\s*(\d+\.?\d*)\s*(%|percent|w|v|a|k|ohm|ω)?\s*$", s.strip().lower())
    if not m:
        return None, None
    return float(m.group(1)), (m.group(2) or "")


def _values_match(required: str, answer_norm: str, tol: float = 0.05) -> bool:
    """Tolerance-aware value matching: 4.191W ≈ 4.2W, 14% ≈ 14 percent ≈ 0.14."""
    req = _norm_text(required)
    if req in answer_norm:
        return True
    rv, ru = _parse_number_unit(req)
    if rv is None:
        return False
    # find all numbers with compatible units in the answer
    for m in re.finditer(r"(\d+\.?\d*)\s*(%|percent|w|v|a|k|ohm|ω)?", answer_norm):
        av = float(m.group(1))
        au = (m.group(2) or "").replace("percent", "%")
        runorm = ru.replace("percent", "%")
        if runorm in ("", au) or au in ("", runorm):
            denom = max(abs(rv), abs(av), 1e-9)
            if abs(rv - av) / denom <= tol:
                return True
            # percent-as-decimal equivalence: 0.14 ↔ 14%
            if runorm == "%" and abs(rv * 100 - av) / max(abs(av), 1e-9) <= tol:
                return True
            if au == "%" and abs(av * 100 - rv) / max(abs(rv), 1e-9) <= tol:
                return True
    return False


def _concepts_match(required: str, answer_stems: set) -> bool:
    req_stems = {_stem(t) for t in re.findall(r"\w+", required.lower()) if len(t) > 1}
    if not req_stems:
        return False
    hit = sum(1 for t in req_stems if t in answer_stems)
    return hit / len(req_stems) >= 0.5


def compute_answer_relevance_v3(answer: str, required_concepts: List[str], required_values: List[str],
                                required_sources: List[str], query: str, retrieved: List[Dict], claims: List[Dict]) -> Dict:
    required_concepts = required_concepts or []
    required_values = required_values or []
    body = strip_boilerplate(answer)
    ans_norm = _norm_text(body)
    ans_stems = {_stem(t) for t in re.findall(r"\w+", ans_norm) if len(t) > 1}

    # Layer 1: stemmed concept coverage (paraphrase-tolerant, boilerplate-free)
    concepts_found = sum(1 for c in required_concepts if _concepts_match(c, ans_stems))
    concept_coverage = concepts_found / max(len(required_concepts), 1) if required_concepts else 0.5

    # Layer 2: tolerance-aware value coverage
    values_found = sum(1 for v in required_values if _values_match(v, ans_norm))
    value_coverage = values_found / max(len(required_values), 1) if required_values else 0.5

    # Layer 3: directness — first sentence must contain a required element
    first = body.split(".")[0].lower() if "." in body else body[:200].lower()
    first_stems = {_stem(t) for t in re.findall(r"\w+", first) if len(t) > 1}
    first_norm = _norm_text(first)
    has_element = (any(_concepts_match(c, first_stems) for c in required_concepts)
                   or any(_values_match(v, first_norm) for v in required_values))
    if has_element:
        directness = 0.9
    elif first.strip().startswith(GENERIC_OPENERS):
        directness = 0.2
    elif 20 < len(first.strip()) < 300:
        directness = 0.5
    else:
        directness = 0.3

    # Layer 4: evidence usage (unchanged semantics from v2, boilerplate-free text)
    has_citation = "[source" in ans_norm
    evidence_usage = 0.9 if has_citation else 0.3
    if has_citation and retrieved:
        overlaps = []
        a_terms = set(re.findall(r"\w+", ans_norm))
        for r in retrieved[:3]:
            r_terms = set(re.findall(r"\w+", r["text"].lower()))
            overlaps.append(len(r_terms.intersection(a_terms)) / max(len(r_terms), 1))
        evidence_usage = 0.5 + 0.4 * min((sum(overlaps) / len(overlaps)) * 3, 1) if overlaps else 0.5

    # Layer 5: completeness + boilerplate penalty (system-added footers bloat answers)
    completeness = (concept_coverage + value_coverage) / 2 if (required_concepts or required_values) else 0.6
    if "compare" in query.lower() and "document" in ans_norm:
        completeness = min(1.0, completeness + 0.2)
    boilerplate_chars = len(answer) - len(body)
    irrelevance_penalty = 0.0
    if boilerplate_chars > 150:
        irrelevance_penalty = 0.15
    expected_len = 100 + 50 * len(required_concepts) + 30 * len(required_values)
    if len(body) > expected_len * 2 and len(required_concepts) < 3:
        irrelevance_penalty = max(irrelevance_penalty, 0.2)

    final = (concept_coverage * 0.3 + value_coverage * 0.2 + directness * 0.2
             + evidence_usage * 0.15 + completeness * 0.15) - irrelevance_penalty
    final = max(0, min(1, final))
    return {
        "concept_coverage": round(concept_coverage, 3),
        "value_coverage": round(value_coverage, 3),
        "directness_score": round(directness, 3),
        "evidence_usage": round(evidence_usage, 3),
        "completeness": round(completeness, 3),
        "irrelevance_penalty": round(irrelevance_penalty, 3),
        "answer_relevance_v3": round(final, 3),
        "required_concepts_found": concepts_found,
        "required_values_found": values_found,
        "metric_version": "v3",
    }
