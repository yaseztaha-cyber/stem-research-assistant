"""Helper for v0.3 evaluation: answer relevance v2, evidence redundancy, etc."""
import re
from typing import List, Dict

def compute_answer_relevance_v2(answer: str, required_concepts: List[str], required_values: List[str], required_sources: List[str], query: str, retrieved: List[Dict], claims: List[Dict]) -> Dict:
    """
    Layered answer relevance v2:
    - Layer 1 required concepts coverage
    - Layer 2 directness (does answer start with direct answer)
    - Layer 3 evidence usage (citations)
    - Layer 4 completeness (covered all required parts)
    - Layer 5 irrelevance penalty (unnecessary content)
    """
    required_concepts = required_concepts or []
    required_values = required_values or []
    required_sources = required_sources or []
    ans_low = answer.lower()

    # Layer 1: concept coverage
    concepts_found = sum(1 for c in required_concepts if c.lower() in ans_low)
    concept_coverage = concepts_found / max(len(required_concepts),1) if required_concepts else 0.5

    # Required values coverage
    values_found = sum(1 for v in required_values if v.lower() in ans_low)
    value_coverage = values_found / max(len(required_values),1) if required_values else 0.5

    # Layer 2: directness - does answer start with direct answer (first sentence contains required concept/value)?
    first_sentence = answer.split(".")[0].lower() if "." in answer else answer[:200].lower()
    directness = 0
    if required_concepts and any(c.lower() in first_sentence for c in required_concepts):
        directness = 0.9
    elif required_values and any(v.lower() in first_sentence for v in required_values):
        directness = 0.9
    elif len(first_sentence.strip()) < 300 and len(first_sentence.strip()) > 20:
        # Generic directness: if first sentence is not verbose intro
        if not first_sentence.startswith("there are several") and not first_sentence.startswith("in this"):
            directness = 0.7
        else:
            directness = 0.3
    else:
        directness = 0.5

    # Layer 3: evidence usage - does answer cite sources?
    has_citation = "[source" in ans_low
    evidence_usage = 0.9 if has_citation else 0.3
    # Also check if citations correspond to retrieved
    if has_citation and retrieved:
        # Check if answer uses retrieved evidence appropriately (term overlap)
        overlap_scores = []
        for r in retrieved[:3]:
            r_terms = set(re.findall(r"\w+", r["text"].lower()))
            a_terms = set(re.findall(r"\w+", answer.lower()))
            overlap = len(r_terms.intersection(a_terms)) / max(len(r_terms),1)
            overlap_scores.append(overlap)
        avg_overlap = sum(overlap_scores)/len(overlap_scores) if overlap_scores else 0
        evidence_usage = 0.5 + 0.4 * min(avg_overlap*3, 1)  # scale

    # Layer 4: completeness - did it cover all required parts?
    completeness = (concept_coverage + value_coverage) / 2 if required_concepts or required_values else 0.6
    # For comparison queries, need both docs
    if "compare" in query.lower() and "document" in ans_low:
        completeness = min(1.0, completeness + 0.2)

    # Layer 5: irrelevance penalty - does answer introduce irrelevant explanations?
    # If answer is very long vs required, penalize
    expected_len = 100 + 50*len(required_concepts) + 30*len(required_values)
    actual_len = len(answer)
    if actual_len > expected_len * 2 and len(required_concepts) < 3:
        irrelevance_penalty = 0.2
    elif "generated" in ans_low and ans_low.count("generated") > 5:
        irrelevance_penalty = 0.15
    else:
        irrelevance_penalty = 0

    # Final weighted
    final = (concept_coverage*0.3 + value_coverage*0.2 + directness*0.2 + evidence_usage*0.15 + completeness*0.15) - irrelevance_penalty
    final = max(0, min(1, final))

    # Also compute legacy relevance (token overlap) for comparison
    q_terms = set(re.findall(r"\w+", query.lower()))
    a_terms = set(re.findall(r"\w+", answer.lower()))
    legacy = len(q_terms.intersection(a_terms)) / max(len(q_terms),1) if q_terms else 0

    return {
        "concept_coverage": round(concept_coverage,3),
        "value_coverage": round(value_coverage,3),
        "directness_score": round(directness,3),
        "evidence_usage": round(evidence_usage,3),
        "completeness": round(completeness,3),
        "irrelevance_penalty": round(irrelevance_penalty,3),
        "answer_relevance_v2": round(final,3),
        "legacy_answer_relevance": round(legacy,3),
        "required_concepts_found": concepts_found,
        "required_values_found": values_found,
    }

def compute_evidence_redundancy(retrieved: List[Dict]) -> Dict:
    if not retrieved:
        return {"unique_pages":0,"unique_sections":0,"unique_documents":0,"duplicate_ratio":0}
    pages = [r.get("page_number") for r in retrieved]
    sections = [r.get("section") for r in retrieved]
    docs = [r.get("document_id") for r in retrieved]
    unique_pages = len(set(pages))
    unique_sections = len(set(sections))
    unique_docs = len(set(docs))
    # Duplicate ratio: how many chunks share same text overlap >0.8
    dup = 0
    for i in range(len(retrieved)):
        for j in range(i+1, len(retrieved)):
            t1 = set(retrieved[i]["text"].lower().split())
            t2 = set(retrieved[j]["text"].lower().split())
            if len(t1.intersection(t2))/max(len(t1.union(t2)),1) > 0.8:
                dup +=1
    duplicate_ratio = dup / max(len(retrieved)*(len(retrieved)-1)/2,1)
    return {
        "unique_pages": unique_pages,
        "unique_sections": unique_sections,
        "unique_documents": unique_docs,
        "duplicate_ratio": round(duplicate_ratio,3),
        "evidence_redundancy": round(duplicate_ratio,3)
    }

def compute_question_coverage(query: str, answer: str, required_concepts: List[str]) -> float:
    # Did answer address what was asked? Check if required concepts appear
    if not required_concepts:
        return 0.5
    ans_low = answer.lower()
    covered = sum(1 for c in required_concepts if c.lower() in ans_low)
    return covered / len(required_concepts)
