from sqlalchemy.orm import Session
from typing import List, Dict
from ..models.human_grade import HumanGrade
from ..models.evaluation import EvaluationCase
import math

DIMENSIONS = ["correctness","relevance","completeness","grounding","citation_quality","directness"]

def validate_scores(payload: Dict) -> Dict:
    for d in DIMENSIONS:
        v = payload.get(d)
        if v is None or not isinstance(v, int) or v < 1 or v > 5:
            raise ValueError(f"{d} must be integer 1-5, got {v!r}")
    if not payload.get("evaluation_case_id"):
        raise ValueError("evaluation_case_id required")
    if not payload.get("answer_text"):
        raise ValueError("answer_text required")
    return payload

def submit_grade(db: Session, payload: Dict) -> HumanGrade:
    validate_scores(payload)
    # Ensure case exists
    case = db.query(EvaluationCase).filter(EvaluationCase.id == payload["evaluation_case_id"]).first()
    if not case:
        raise ValueError("evaluation case not found")
    g = HumanGrade(
        evaluation_case_id=payload["evaluation_case_id"],
        answer_text=payload["answer_text"],
        source_ids=payload.get("source_ids"),
        grader_id=payload.get("grader_id", "anonymous"),
        correctness=payload["correctness"],
        relevance=payload["relevance"],
        completeness=payload["completeness"],
        grounding=payload["grounding"],
        citation_quality=payload["citation_quality"],
        directness=payload["directness"],
        comments=payload.get("comments"),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g

def consensus_for_case(db: Session, case_id: str) -> Dict:
    grades = db.query(HumanGrade).filter(HumanGrade.evaluation_case_id == case_id).all()
    if not grades:
        return {"case_id": case_id, "grader_count": 0}
    out = {"case_id": case_id, "grader_count": len(grades)}
    for d in DIMENSIONS:
        vals = [getattr(g, d) for g in grades]
        mean = sum(vals)/len(vals)
        s = sorted(vals)
        n = len(s)
        median = s[n//2] if n % 2 == 1 else (s[n//2-1]+s[n//2])/2
        # mean absolute difference (agreement)
        mad = sum(abs(v-mean) for v in vals)/len(vals) if len(vals)>1 else 0.0
        out[d] = {"mean": round(mean,2), "median": median, "mad": round(mad,3), "values": vals}
    # consensus score = mean of dimension means
    out["consensus_score"] = round(sum(out[d]["mean"] for d in DIMENSIONS)/len(DIMENSIONS), 2)
    # agreement flag: mad <= 1.0 on all dimensions
    out["agreement"] = all(out[d]["mad"] <= 1.0 for d in DIMENSIONS) if len(grades) > 1 else None
    return out

def spearman_corr(xs: List[float], ys: List[float]) -> float:
    # Rank-based Spearman without scipy
    n = len(xs)
    if n < 3:
        return 0.0
    def ranks(v):
        # average ranks for ties
        sorted_idx = sorted(range(n), key=lambda i: v[i])
        r = [0]*n
        i = 0
        while i < n:
            j = i
            while j+1 < n and v[sorted_idx[j+1]] == v[sorted_idx[i]]:
                j += 1
            avg = (i+j)/2 + 1
            for k in range(i, j+1):
                r[sorted_idx[k]] = avg
            i = j+1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx)/n, sum(ry)/n
    num = sum((a-mx)*(b-my) for a,b in zip(rx,ry))
    den = math.sqrt(sum((a-mx)**2 for a in rx) * sum((b-my)**2 for b in ry))
    if den == 0:
        return 0.0
    return round(num/den, 3)

def metric_validation(db: Session) -> Dict:
    """Correlate automated metrics with human ratings (Spearman, ordinal)."""
    from .evaluation import run_evaluation
    # Get automated per-case metrics
    auto = run_evaluation(db)
    auto_by_q = {c["question"]: c for c in auto["cases"]}
    # Get consensus per case with grades
    cases = db.query(EvaluationCase).all()
    pairs = {"answer_relevance_v2": [], "answer_relevance_v3": [], "human_relevance": [], "groundedness": [], "human_grounding": [], "citation_accuracy": [], "human_citation": [], "question_coverage": [], "human_correctness": [], "human_completeness": []}
    # For question coverage we approximate with answer_relevance_v2 concept coverage? Use v2 details
    for case in cases:
        cons = consensus_for_case(db, case.id)
        if cons.get("grader_count", 0) == 0:
            continue
        a = auto_by_q.get(case.question)
        if not a:
            continue
        pairs["answer_relevance_v2"].append(a.get("answer_relevance_v2", 0))
        pairs["answer_relevance_v3"].append(a.get("answer_relevance_v3", a.get("answer_relevance_v2", 0)))
        pairs["human_relevance"].append(cons["relevance"]["mean"])
        pairs["human_completeness"].append(cons["completeness"]["mean"])
        pairs["groundedness"].append(a.get("groundedness", 0))
        pairs["human_grounding"].append(cons["grounding"]["mean"])
        pairs["citation_accuracy"].append(a.get("citation_accuracy", 0))
        pairs["human_citation"].append(cons["citation_quality"]["mean"])
        # question coverage proxy: use v2 completeness if available
        v2d = a.get("v2_details", {}) or {}
        pairs["question_coverage"].append(v2d.get("completeness", a.get("answer_relevance_v2", 0)))
        pairs["human_correctness"].append(cons["correctness"]["mean"])
    n = len(pairs["human_relevance"])
    result = {"n_graded_cases": n}
    if n < 3:
        result["warning"] = "fewer than 3 graded cases; correlation not meaningful"
        result["correlations"] = {}
        return result
    result["correlations"] = {
        "answer_relevance_v2_vs_human_relevance": spearman_corr(pairs["answer_relevance_v2"], pairs["human_relevance"]),
        "answer_relevance_v3_vs_human_relevance": spearman_corr(pairs["answer_relevance_v3"], pairs["human_relevance"]),
        "answer_relevance_v3_vs_human_completeness": spearman_corr(pairs["answer_relevance_v3"], pairs["human_completeness"]),
        "groundedness_vs_human_grounding": spearman_corr(pairs["groundedness"], pairs["human_grounding"]),
        "citation_accuracy_vs_human_citation": spearman_corr(pairs["citation_accuracy"], pairs["human_citation"]),
        "question_coverage_vs_human_correctness": spearman_corr(pairs["question_coverage"], pairs["human_correctness"]),
    }
    result["interpretation"] = "Spearman rho on ordinal 1-5 human means vs automated 0-1 scores. |rho|<0.3 weak, 0.3-0.6 moderate, >0.6 strong."
    return result

def export_gold_set(db: Session) -> Dict:
    cases = db.query(EvaluationCase).all()
    items = []
    for case in cases:
        cons = consensus_for_case(db, case.id)
        if cons.get("grader_count", 0) == 0:
            continue
        grades = db.query(HumanGrade).filter(HumanGrade.evaluation_case_id == case.id).all()
        # Use most recent answer text as system_answer (or first)
        ans = grades[0].answer_text if grades else ""
        items.append({
            "question": case.question,
            "system_answer": ans[:2000],
            "source_ids": grades[0].source_ids if grades else [],
            "scores": {d: cons[d] for d in DIMENSIONS},
            "grader_count": cons["grader_count"],
            "consensus_score": cons["consensus_score"],
            "category": case.category,
        })
    return {"count": len(items), "items": items, "note": "Anonymized; no personal data. Only cases with >=1 human grade."}

def retrieval_vs_answer_analysis(db: Session) -> List[Dict]:
    from .evaluation import run_evaluation
    auto = run_evaluation(db)
    out = []
    for c in auto["cases"]:
        cons = consensus_for_case(db, c["case_id"])
        retrieval = "PASS" if c["retrieval_recall"] == 1 else "FAIL"
        evidence = (c.get("evidence_sufficiency") or {}).get("status", "unknown")
        citation = "PASS" if c["citation_accuracy"] >= 0.5 else "FAIL"
        if cons.get("grader_count", 0) > 0:
            human_rel = cons["relevance"]["mean"]
            answer = "PASS" if human_rel >= 3.5 else "FAIL"
        else:
            # Fallback to automated v2
            answer = "PASS" if c.get("answer_relevance_v2", 0) >= 0.6 else "FAIL"
            human_rel = None
        out.append({
            "case_id": c["case_id"],
            "question": c["question"],
            "category": c["category"],
            "retrieval": retrieval,
            "evidence": evidence,
            "citation": citation,
            "answer": answer,
            "human_relevance": human_rel,
            "answer_relevance_v2": c.get("answer_relevance_v2"),
            "failure_type": c.get("failure_type"),
        })
    return out
