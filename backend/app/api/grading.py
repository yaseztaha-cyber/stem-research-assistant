from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict
from ..database import get_db
from ..services.human_eval import submit_grade, consensus_for_case, metric_validation, export_gold_set, retrieval_vs_answer_analysis, DIMENSIONS
from ..models.evaluation import EvaluationCase
from ..models.human_grade import HumanGrade
from ..models.pairwise import PairwiseGrade

router = APIRouter(prefix="/grading", tags=["grading"])

class GradeIn(BaseModel):
    evaluation_case_id: str
    answer_text: str
    source_ids: Optional[List[str]] = None
    grader_id: Optional[str] = "anonymous"
    correctness: int
    relevance: int
    completeness: int
    grounding: int
    citation_quality: int
    directness: int
    comments: Optional[str] = None

@router.get("/cases")
def list_cases(db: Session = Depends(get_db), include_answers: bool = Query(False), top_k: int = Query(5),
               shuffle: bool = Query(False), seed: int = Query(7)):
    cases = db.query(EvaluationCase).order_by(EvaluationCase.category).all()
    out = []
    for c in cases:
        grades = db.query(HumanGrade).filter(HumanGrade.evaluation_case_id == c.id).count()
        item = {
            "id": c.id, "question": c.question, "category": c.category,
            "expected_answer": c.expected_answer, "expected_concept": c.expected_concept,
            "grade_count": grades,
            "required_concepts": c.required_concepts, "required_values": c.required_values,
        }
        if include_answers:
            # Generate answer on demand (cached retrieval)
            try:
                import asyncio
                from ..services.rag import rag_query
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                res = loop.run_until_complete(rag_query(db, c.question, top_k=top_k, document_ids=c.document_ids))
                item["system_answer"] = res.get("answer", "")[:3000]
                item["citations"] = res.get("citations", [])[:4]
                item["claims"] = res.get("claims", [])[:8]
                item["retrieval_trace"] = res.get("retrieval_trace", {})
                item["query_type"] = res.get("query_type")
            except Exception as e:
                item["system_answer"] = f" generation failed: {e}"
        out.append(item)
    if shuffle:
        import random
        rng = random.Random(seed)
        rng.shuffle(out)
    return out

@router.post("/grade")
def grade(payload: GradeIn, db: Session = Depends(get_db)):
    g = submit_grade(db, payload.model_dump())
    return {"id": g.id, "case_id": g.evaluation_case_id, "grader": g.grader_id}

@router.get("/grades")
def grades(case_id: str = Query(None), db: Session = Depends(get_db)):
    q = db.query(HumanGrade)
    if case_id:
        q = q.filter(HumanGrade.evaluation_case_id == case_id)
    rows = q.order_by(HumanGrade.created_at.desc()).limit(200).all()
    return [{
        "id": g.id, "case_id": g.evaluation_case_id, "grader_id": g.grader_id,
        "correctness": g.correctness, "relevance": g.relevance, "completeness": g.completeness,
        "grounding": g.grounding, "citation_quality": g.citation_quality, "directness": g.directness,
        "comments": g.comments, "created_at": str(g.created_at),
    } for g in rows]

@router.get("/consensus")
def consensus(case_id: str = Query(None), db: Session = Depends(get_db)):
    if case_id:
        return consensus_for_case(db, case_id)
    cases = db.query(EvaluationCase).all()
    return [consensus_for_case(db, c.id) for c in cases if db.query(HumanGrade).filter(HumanGrade.evaluation_case_id == c.id).count() > 0]

@router.get("/correlation")
def correlation(db: Session = Depends(get_db)):
    return metric_validation(db)

@router.get("/gold-set")
def gold_set(db: Session = Depends(get_db)):
    return export_gold_set(db)

@router.get("/retrieval-vs-answer")
def rva(db: Session = Depends(get_db)):
    return retrieval_vs_answer_analysis(db)

class PairwiseIn(BaseModel):
    evaluation_case_id: str
    answer_a: str
    answer_b: str
    system_a: str
    system_b: str
    grader_id: Optional[str] = "anonymous"
    preferred_answer: str  # A | B | tie
    reason: Optional[str] = None

@router.post("/pairwise")
def pairwise(payload: PairwiseIn, db: Session = Depends(get_db)):
    if payload.preferred_answer not in ("A", "B", "tie"):
        from fastapi import HTTPException
        raise HTTPException(400, "preferred_answer must be A, B, or tie")
    case = db.query(EvaluationCase).filter(EvaluationCase.id == payload.evaluation_case_id).first()
    if not case:
        from fastapi import HTTPException
        raise HTTPException(404, "evaluation case not found")
    g = PairwiseGrade(
        evaluation_case_id=payload.evaluation_case_id,
        answer_a=payload.answer_a, answer_b=payload.answer_b,
        system_a=payload.system_a, system_b=payload.system_b,
        grader_id=payload.grader_id or "anonymous",
        preferred_answer=payload.preferred_answer, reason=payload.reason)
    db.add(g)
    db.commit()
    db.refresh(g)
    return {"id": g.id, "case_id": g.evaluation_case_id}

@router.get("/pairwise")
def pairwise_list(case_id: str = Query(None), db: Session = Depends(get_db)):
    q = db.query(PairwiseGrade)
    if case_id:
        q = q.filter(PairwiseGrade.evaluation_case_id == case_id)
    rows = q.order_by(PairwiseGrade.created_at.desc()).limit(200).all()
    # Never reveal system mapping in list view? Grader already graded; show mapping for analysis.
    return [{"id": g.id, "case_id": g.evaluation_case_id, "grader_id": g.grader_id,
             "system_a": g.system_a, "system_b": g.system_b, "preferred_answer": g.preferred_answer,
             "reason": g.reason, "created_at": str(g.created_at)} for g in rows]

@router.get("/pairwise/summary")
def pairwise_summary(db: Session = Depends(get_db)):
    """Wins per system pair (unblinded only after grading)."""
    from collections import Counter
    rows = db.query(PairwiseGrade).all()
    tally: Dict[str, Counter] = {}
    for g in rows:
        pair = f"{g.system_a} vs {g.system_b}"
        c = tally.setdefault(pair, Counter())
        if g.preferred_answer == "A":
            c[g.system_a] += 1
        elif g.preferred_answer == "B":
            c[g.system_b] += 1
        else:
            c["tie"] += 1
    return {k: dict(v) for k, v in tally.items()}

class PairRequest(BaseModel):
    evaluation_case_id: str
    system_a: Optional[Dict] = None  # {llm, embedding, reranker, prompt_version}
    system_b: Optional[Dict] = None
    seed: Optional[int] = 7

# Server-side blinded pair store (local-only tool; mapping hidden until graded)
_PAIR_STORE: Dict[str, Dict] = {}

def _default_systems():
    return ({"llm": "mock", "embedding": "tfidf", "reranker": "simple", "prompt_version": "v3"},
            {"llm": "mock", "embedding": "dense", "reranker": "cross_encoder", "prompt_version": "v3"})

@router.post("/pair")
async def make_pair(payload: PairRequest, db: Session = Depends(get_db)):
    """Generate a blinded A/B pair for one case. Systems default to
    mock:tfidf+simple vs mock:dense+ce (retrieval-contrast experiment)."""
    import random as _random
    import asyncio as _asyncio
    case = db.query(EvaluationCase).filter(EvaluationCase.id == payload.evaluation_case_id).first()
    if not case:
        from fastapi import HTTPException
        raise HTTPException(404, "evaluation case not found")
    sys_a = payload.system_a or _default_systems()[0]
    sys_b = payload.system_b or _default_systems()[1]
    from ..services.generation_experiment import run_ab_case
    from ..config import settings as _settings
    # Backend runs each system sequentially; retrieval config from system spec
    answers = {}
    for tag, sys in (("A", sys_a), ("B", sys_b)):
        if (sys.get("llm") or "mock") != "mock":
            from fastapi import HTTPException
            raise HTTPException(400, "pair endpoint currently supports mock llm only (local/real need long runtimes; use scripts)")
        res = await run_ab_case(
            db, case.question,
            {"embedding": sys.get("embedding", "tfidf"), "reranker": sys.get("reranker", "simple")},
            ["mock"], prompt_version=sys.get("prompt_version", "v3"),
            answer_length="brief", top_k=5, strict=False,
            required_elements=(case.required_concepts or []) + (case.required_values or []))
        arm = res["arms"]["mock"]
        answers[tag] = {"answer": arm["answer"], "system": f"mock:{sys.get('embedding')}+{sys.get('reranker')}:{sys.get('prompt_version')}",
                        "citations": res.get("retrieved", [])[:3], "query_type": res.get("query_type")}
    rng = _random.Random(payload.seed)
    order = ["A", "B"]
    rng.shuffle(order)
    import uuid as _uuid
    pair_id = str(_uuid.uuid4())
    _PAIR_STORE[pair_id] = {"case_id": case.id, "first": order[0], "second": order[1],
                            "systems": {"A": answers["A"]["system"], "B": answers["B"]["system"]},
                            "answers": {"A": answers["A"]["answer"], "B": answers["B"]["answer"]}}
    first, second = order
    return {"pair_id": pair_id, "case_id": case.id, "question": case.question, "category": case.category,
            "answer_a": answers[first]["answer"], "answer_b": answers[second]["answer"],
            "citations_a": [{"document": c.get("document_name"), "page": c.get("page_number")} for c in answers[first]["citations"]],
            "citations_b": [{"document": c.get("document_name"), "page": c.get("page_number")} for c in answers[second]["citations"]]}

class PairwiseBlindIn(BaseModel):
    pair_id: str
    grader_id: Optional[str] = "anonymous"
    preferred_answer: str
    reason: Optional[str] = None

@router.post("/pairwise-blind")
def pairwise_blind(payload: PairwiseBlindIn, db: Session = Depends(get_db)):
    if payload.preferred_answer not in ("A", "B", "tie"):
        from fastapi import HTTPException
        raise HTTPException(400, "preferred_answer must be A, B, or tie")
    mapping = _PAIR_STORE.get(payload.pair_id)
    if not mapping:
        from fastapi import HTTPException
        raise HTTPException(404, "pair expired or unknown; regenerate the pair")
    g = PairwiseGrade(
        evaluation_case_id=mapping["case_id"],
        answer_a=mapping["answers"]["A"], answer_b=mapping["answers"]["B"],
        system_a=mapping["systems"]["A"], system_b=mapping["systems"]["B"],
        grader_id=payload.grader_id or "anonymous",
        preferred_answer=payload.preferred_answer, reason=payload.reason)
    db.add(g)
    db.commit()
    db.refresh(g)
    return {"id": g.id, "case_id": g.evaluation_case_id}

@router.get("/progress")
def progress(db: Session = Depends(get_db)):
    """Grader progress: remaining cases, double-graded status (v0.5 §39)."""
    from ..models.human_grade import HumanGrade as HG
    cases = db.query(EvaluationCase).all()
    total = len(cases)
    graded = double = 0
    ungraded_ids = []
    single_ids = []
    for c in cases:
        graders = {g.grader_id for g in db.query(HG).filter(HG.evaluation_case_id == c.id).all()}
        # Count distinct human passes (exclude test-grader)
        graders = {g for g in graders if g != "test-grader"}
        if not graders:
            ungraded_ids.append(c.id)
        else:
            graded += 1
            if len(graders) >= 2:
                double += 1
            else:
                single_ids.append(c.id)
    return {"total": total, "graded": graded, "double_graded": double,
            "remaining": total - graded, "ungraded_ids": ungraded_ids, "single_ids": single_ids}
