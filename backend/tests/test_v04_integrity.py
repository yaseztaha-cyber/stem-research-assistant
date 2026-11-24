import backend.app.models.all_models
from backend.app.database import SessionLocal

def test_preflight():
    from backend.app.services.preflight import run_preflight
    ok, results = run_preflight()
    names = [n for n, _, _ in results]
    assert "Python" in names and "Database" in names and "Evaluation dataset" in names
    # Returns tuple, doesn't raise
    assert isinstance(ok, bool)

def test_strict_benchmark_no_fallback_mislabel():
    """Strict mode must never record fallback results under requested config.
    Uses a bogus model name so strict Dense configs FAIL fast without heavy compute."""
    from backend.app.services.evaluation import run_benchmark_matrix
    from backend.app.config import settings
    db = SessionLocal()
    orig_model = settings.dense_embedding_model
    orig_ce = settings.cross_encoder_model
    try:
        settings.dense_embedding_model = "nonexistent-model-xyz-v04-test"
        settings.cross_encoder_model = "nonexistent-model-xyz-v04-test"
        from backend.app.core.embedding_provider import reset_embedding_provider
        from backend.app.core.reranker import reset_reranker
        reset_embedding_provider(); reset_reranker()
        out = run_benchmark_matrix(db, strict=True)
        assert "TFIDF+Simple" in out and "Dense+CrossEncoder" in out
        for name, res in out.items():
            assert "fallback" in res, f"{name} missing fallback flag"
            assert "requested_embedding_provider" in res
            assert "active_embedding_provider" in res
            if res.get("error"):
                # FAILED configs must have no summary score
                assert "summary" not in res, f"{name} has both error and summary"
            else:
                # Passed configs: active must equal requested in strict mode
                assert res["active_embedding_provider"] == res["requested_embedding_provider"], f"{name} fallback in strict mode"
                assert res["active_reranker"] == res["requested_reranker"], f"{name} reranker fallback in strict mode"
        # Dense configs must have FAILED (model unavailable), TFIDF must have passed
        assert "summary" in out["TFIDF+Simple"]
        assert "summary" not in out["Dense+Simple"] or out["Dense+Simple"].get("error")
    finally:
        settings.dense_embedding_model = orig_model
        settings.cross_encoder_model = orig_ce
        from backend.app.core.embedding_provider import reset_embedding_provider
        from backend.app.core.reranker import reset_reranker
        reset_embedding_provider(); reset_reranker()

def test_configuration_identity():
    from backend.app.core.embedding_provider import get_active_embedding_identity
    from backend.app.core.reranker import get_active_reranker_identity
    emb = get_active_embedding_identity()
    assert "requested_embedding_provider" in emb and "active_embedding_provider" in emb and "fallback" in emb
    rer = get_active_reranker_identity()
    assert "requested_reranker" in rer and "active_reranker" in rer and "fallback" in rer

def test_dense_model_availability():
    from sentence_transformers import SentenceTransformer
    from backend.app.config import settings
    m = SentenceTransformer(settings.dense_embedding_model, local_files_only=True)
    assert m.get_embedding_dimension() == 384

def test_cross_encoder_availability():
    from sentence_transformers import CrossEncoder
    from backend.app.config import settings
    m = CrossEncoder(settings.cross_encoder_model, local_files_only=True)
    scores = m.predict([("what is power?", "Power is P = VI")])
    assert len(scores) == 1

def test_grader_storage_and_validation():
    from backend.app.services.human_eval import submit_grade
    from backend.app.models.evaluation import EvaluationCase
    from backend.app.models.human_grade import HumanGrade
    import pytest
    db = SessionLocal()
    case = db.query(EvaluationCase).first()
    assert case is not None
    # Invalid score must raise
    with pytest.raises(ValueError):
        submit_grade(db, {"evaluation_case_id": case.id, "answer_text": "x", "correctness": 6, "relevance": 3, "completeness": 3, "grounding": 3, "citation_quality": 3, "directness": 3})
    # Valid submit
    g = submit_grade(db, {"evaluation_case_id": case.id, "answer_text": "test answer v04", "grader_id": "test-grader", "correctness": 4, "relevance": 4, "completeness": 3, "grounding": 4, "citation_quality": 4, "directness": 5})
    assert g.id is not None
    # Versioning: second submit creates new row, doesn't overwrite
    g2 = submit_grade(db, {"evaluation_case_id": case.id, "answer_text": "test answer v04b", "grader_id": "test-grader", "correctness": 3, "relevance": 3, "completeness": 3, "grounding": 3, "citation_quality": 3, "directness": 3})
    assert g2.id != g.id
    # Cleanup test rows
    db.query(HumanGrade).filter(HumanGrade.grader_id == "test-grader").delete()
    db.commit()

def test_consensus_calculation():
    from backend.app.services.human_eval import consensus_for_case
    from backend.app.models.evaluation import EvaluationCase
    db = SessionLocal()
    # Use a case with developer grades (12 seeded)
    from backend.app.models.human_grade import HumanGrade
    row = db.query(HumanGrade).filter(HumanGrade.grader_id == "developer-grader-a").first()
    assert row is not None
    cons = consensus_for_case(db, row.evaluation_case_id)
    assert cons["grader_count"] >= 2
    assert "consensus_score" in cons
    assert 1 <= cons["consensus_score"] <= 5
    assert "mean" in cons["correctness"] and "median" in cons["correctness"]

def test_metric_correlation():
    from backend.app.services.human_eval import metric_validation, spearman_corr
    # Unit: perfect correlation
    assert spearman_corr([1,2,3,4],[1,2,3,4]) == 1.0
    assert spearman_corr([1,2,3],[3,2,1]) == -1.0
    # Integration: with seeded developer grades, n>=3 so correlations computed
    db = SessionLocal()
    res = metric_validation(db)
    assert res["n_graded_cases"] >= 3
    assert "correlations" in res

def test_cold_warm_latency_tracking():
    from backend.app.services.retrieval import retrieve_with_trace
    from backend.app.services.cache import retrieval_cache
    from backend.app.config import settings
    from backend.app.core.embedding_provider import reset_embedding_provider
    from backend.app.core.reranker import reset_reranker
    db = SessionLocal()
    retrieval_cache.invalidate("retrieval")
    r1, t1 = retrieve_with_trace(db, "What is the Seebeck effect?", top_k=3)
    # First call: cold (no cache hit flag or False)
    assert t1["latency"]["total_ms"] >= 0
    r2, t2 = retrieve_with_trace(db, "What is the Seebeck effect?", top_k=3)
    # Second identical call should be cache hit (warm)
    assert t2.get("cache_hit") == True or t2.get("latency",{}).get("cache_hit") == True

def test_failure_classification():
    from backend.app.services.evaluation import run_evaluation
    db = SessionLocal()
    out = run_evaluation(db)
    valid_types = {None, "wrong_document","wrong_page","wrong_section","semantic_mismatch","keyword_mismatch","duplicate_evidence","reranker_failure","metadata_failure","chunking_failure","partial","no_candidates"}
    for c in out["cases"]:
        assert c.get("failure_type") in valid_types or c.get("failure_type") is None

def test_p95_in_summary():
    from backend.app.services.evaluation import run_evaluation
    db = SessionLocal()
    out = run_evaluation(db)
    s = out["summary"]
    assert "p95_latency_ms" in s and "median_latency_ms" in s
    assert s["p95_latency_ms"] >= s["median_latency_ms"] >= 0
