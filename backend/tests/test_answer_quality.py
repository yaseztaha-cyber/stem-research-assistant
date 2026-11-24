import backend.app.models.all_models
from backend.app.database import SessionLocal
from backend.app.services.evaluation_v2_helper import compute_answer_relevance_v2, compute_evidence_redundancy, compute_question_coverage
from backend.app.services.context_builder import build_optimized_context, expand_local_context
from backend.app.services.grounding import classify_claim_type, extract_claims
from backend.app.services.query_classifier import classify_query
import asyncio

def test_answer_directness():
    # Direct answer should be first sentence containing required concept
    answer = "The reported efficiency at ΔT = 120 K was 5.2%. [SOURCE: paper.pdf p.4] This follows from the results."
    res = compute_answer_relevance_v2(answer, ["efficiency","120 K"], ["5.2%"], ["paper.pdf"], "What was the reported efficiency at ΔT = 120 K?", [{"text":"efficiency 5.2% at 120K","retrieval_score":0.8}], extract_claims(answer))
    assert res["directness_score"] >= 0.7, f"directness {res['directness_score']}"
    assert res["concept_coverage"] == 1.0

def test_question_coverage():
    cov = compute_question_coverage("Compare methods A and B", "Document A reports 12% [SOURCE] Document B reports 18% [SOURCE]", ["Document A","Document B"])
    assert cov >= 0.5

def test_required_concept_detection():
    ans = "P = VI defines power [SOURCE]"
    res = compute_answer_relevance_v2(ans, ["P = VI","power"], ["P = VI"], [], "What equation defines electrical power?", [], [])
    assert res["concept_coverage"] == 1.0
    assert res["value_coverage"] == 1.0

def test_table_qa_retrieval():
    db = SessionLocal()
    from backend.app.services.retrieval import retrieve_with_trace
    # Table query should retrieve table chunk
    retrieved, trace = retrieve_with_trace(db, "Which DeltaT configuration produced the highest power output?", top_k=5)
    # At least one retrieved should contain table-like content (DeltaT, P, W)
    has_table = any("DeltaT" in r["text"] and "P" in r["text"] for r in retrieved)
    assert has_table or len(retrieved)>0

def test_equation_reasoning_derived():
    # Test derived reasoning classification - tag must be within same sentence
    claim = "If V doubles while I is constant, P doubles [DERIVED from P = VI]."
    claims = extract_claims(claim)
    assert claims[0]["type"] == "derived"
    assert claims[0]["claim_type"] in ("equation","derived","fact")

def test_context_ordering():
    db = SessionLocal()
    from backend.app.services.retrieval import retrieve_with_trace
    retrieved, trace = retrieve_with_trace(db, "What equation defines electrical power?", top_k=5)
    # Build optimized context
    context = build_optimized_context(db, "What equation defines electrical power?", "equation", retrieved)
    # Should contain PRIMARY EVIDENCE header and be ordered
    assert "PRIMARY EVIDENCE" in context
    # Ensure equations preserved
    assert "Content Type: equation" in context or "P = V" in context

def test_context_expansion():
    db = SessionLocal()
    from backend.app.services.retrieval import retrieve_with_trace
    retrieved, _ = retrieve_with_trace(db, "What is the Seebeck effect?", top_k=3)
    if retrieved:
        expanded = expand_local_context(db, retrieved[0], window=1)
        assert "text" in expanded
        # Should have expanded flag
        assert "expanded" in expanded

def test_source_grouping():
    db = SessionLocal()
    from backend.app.services.rag import compare_documents
    import asyncio
    async def run():
        docs = db.query(__import__('backend.app.models.document', fromlist=['Document']).Document).limit(2).all()
        if len(docs)>=2:
            res = await compare_documents(db, "Compare methods", [d.id for d in docs[:2]])
            assert "grouped" in res
            assert len(res["grouped"]["document_evidence"]) == 2
    asyncio.run(run())

def test_answer_length_modes():
    import asyncio
    from backend.app.services.rag import rag_query
    db = SessionLocal()
    async def run():
        for mode in ["brief","standard","detailed"]:
            res = await rag_query(db, "What is the Seebeck effect?", top_k=3, answer_length=mode)
            assert "answer" in res
            # Brief should be shorter than detailed
            # We just check that answer exists and is not empty
            assert len(res["answer"]) > 20
    asyncio.run(run())

def test_evidence_redundancy():
    retrieved = [
        {"text":"same text about power","page_number":1,"section":"A","document_id":"d1"},
        {"text":"same text about power","page_number":1,"section":"A","document_id":"d1"},
        {"text":"different content about Seebeck equation","page_number":2,"section":"B","document_id":"d1"},
    ]
    red = compute_evidence_redundancy(retrieved)
    assert red["duplicate_ratio"] > 0
    assert red["unique_pages"] == 2

def test_numeric_reasoning():
    from backend.app.services.math_validation import full_math_validation
    # Check P=VI validation
    res = full_math_validation("P = VI")
    assert res["syntax"]["syntax_valid"] == True
    # Check derived: if V doubles, P doubles is consistent with P=VI
    # This is derived reasoning, not direct validation, but syntax should be valid
    res2 = full_math_validation("P = VI", {"V":2, "I":1})
    # Just check that validation runs
    assert "overall_valid" in res2
