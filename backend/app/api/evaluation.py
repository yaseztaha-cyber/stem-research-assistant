from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.evaluation import run_evaluation, seed_evaluation_cases, get_baseline_comparison, run_benchmark_matrix, ablation_study
from ..services.preflight import run_preflight

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

@router.post("/seed")
def seed(db: Session = Depends(get_db)):
    seed_evaluation_cases(db, expand=True)
    return {"message": "seeded expanded 50+ cases"}

@router.get("/run")
def run(db: Session = Depends(get_db), use_real_rag: bool = Query(False)):
    seed_evaluation_cases(db, expand=True)
    return run_evaluation(db, use_real_rag=use_real_rag)

@router.get("/benchmark")
def benchmark(db: Session = Depends(get_db), strict: bool = Query(False)):
    seed_evaluation_cases(db, expand=True)
    cur = run_evaluation(db)
    comp = get_baseline_comparison(cur["summary"])
    # Also include strict matrix if requested
    matrix = run_benchmark_matrix(db, strict=strict)
    return {"current": cur, "comparison": comp, "baseline_path": "docs/evaluation/v0.1-baseline.json", "matrix": matrix, "strict": strict}

@router.get("/matrix")
def matrix(db: Session = Depends(get_db), strict: bool = Query(False)):
    seed_evaluation_cases(db, expand=True)
    return run_benchmark_matrix(db, strict=strict)

@router.get("/preflight")
def preflight():
    passed, results = run_preflight()
    return {"passed": passed, "checks": [{"name": n, "passed": p, "message": m} for n,p,m in results]}

@router.get("/ablation")
def ablation(db: Session = Depends(get_db)):
    seed_evaluation_cases(db, expand=True)
    return ablation_study(db)

@router.get("/error-analysis")
def error_analysis(db: Session = Depends(get_db)):
    seed_evaluation_cases(db, expand=True)
    res = run_evaluation(db)
    failures = [c for c in res["cases"] if c.get("failure_type")]
    # Classify per spec: wrong_document, wrong_section, wrong_page, semantic_mismatch, keyword_mismatch, duplicate_evidence, reranker_failure, metadata_failure, chunking_failure
    analysis = []
    for c in res["cases"]:
        if c["retrieval_recall"]==0 or c["recall_at_k"]==0:
            ft = c.get("failure_type","unknown")
            analysis.append({
                "case_id": c["case_id"],
                "question": c["question"],
                "category": c["category"],
                "expected_page": c["expected_page"],
                "expected_concept": c["expected_concept"],
                "retrieved_pages": c["retrieved_pages"],
                "failure_type": ft,
                "retrieved_chunks": c["retrieved_chunks"][:3],
                "trace": c.get("trace",{}),
            })
    return {"failures": analysis, "total_failed": len(analysis), "total_cases": len(res["cases"])} 
