"""v0.5 tests: real-provider strictness, prompt registry, answer plan,
generation validation, numeric/derived reasoning, pairwise/blind grading,
metric v3, reproducibility. Deterministic; no model downloads."""
import backend.app.models.all_models  # noqa
from backend.app.database import SessionLocal


def test_strict_real_refuses_without_fallback():
    from backend.app.config import settings
    from backend.app.core.llm_provider import get_llm_provider, RealLLMUnavailable, reset_llm_provider
    orig, orig_key, orig_base = settings.llm_provider, settings.llm_api_key, settings.llm_base_url
    try:
        settings.llm_provider = "real"
        settings.llm_api_key = None
        settings.llm_base_url = "https://api.openai.com/v1"
        reset_llm_provider()
        try:
            get_llm_provider(strict=True)
            raised = False
        except RealLLMUnavailable:
            raised = True
        assert raised, "strict real benchmark must refuse, not fall back"
    finally:
        settings.llm_provider, settings.llm_api_key, settings.llm_base_url = orig, orig_key, orig_base
        reset_llm_provider()


def test_strict_local_refuses_for_missing_model():
    from backend.app.config import settings
    from backend.app.core.llm_provider import get_llm_provider, RealLLMUnavailable, reset_llm_provider
    orig = settings.llm_hf_model
    orig_p = settings.llm_provider
    try:
        settings.llm_provider = "local"
        settings.llm_hf_model = "nonexistent-model-xyz-v05"
        reset_llm_provider()
        try:
            get_llm_provider(strict=True)
            raised = False
        except RealLLMUnavailable:
            raised = True
        assert raised
    finally:
        settings.llm_hf_model = orig
        settings.llm_provider = orig_p
        reset_llm_provider()


def test_provider_identity_distinguishes_mock_real():
    from backend.app.config import settings
    from backend.app.core.llm_provider import get_active_llm_identity, reset_llm_provider
    orig = settings.llm_provider
    try:
        settings.llm_provider = "mock"
        reset_llm_provider()
        ident = get_active_llm_identity()
        assert ident["active_llm_provider"] == "mock" and ident["fallback"] is False
        settings.llm_provider = "real"
        reset_llm_provider()
        ident = get_active_llm_identity()
        # No key configured in CI: either refused (active none) or mock fallback flagged
        assert ident["requested_llm_provider"] == "real"
        assert ident["fallback"] is True or ident["active_llm_provider"] in ("none", "mock")
    finally:
        settings.llm_provider = orig
        reset_llm_provider()


def test_prompt_registry_versions():
    from backend.app.prompts import build_prompt_for_version, PROMPT_VERSIONS
    assert set(PROMPT_VERSIONS) == {"v1", "v2", "v3"}
    ctx = "SOURCE 1\nDocument: paper.pdf\nPage: 7\nSection: Results\nChunk: c1\nContent:\nOutput rose 14%.\n---"
    for v in PROMPT_VERSIONS:
        p = build_prompt_for_version(v, "What rose?", ctx, None, True, "experimental_result", "brief", None)
        assert "Query Type:" in p and "Question:" in p  # mock-parseable markers
    # Unknown version falls back to v3 (contains answer plan block)
    p = build_prompt_for_version("v9", "Q?", ctx)
    assert "ANSWER PLAN" in p
    assert "ANSWER PLAN" not in build_prompt_for_version("v1", "Q?", ctx)


def test_answer_plan_generation():
    from backend.app.prompts.registry import build_answer_plan
    retrieved = [{"chunk_id": "c1"}, {"chunk_id": "c2"}]
    plan = build_answer_plan("What efficiency was reported at 120K?", "experimental_result", retrieved, ["5.2%"])
    assert plan["question_type"] == "experimental_result"
    assert "5.2%" in plan["required_elements"]
    assert plan["evidence_ids"] == ["c1", "c2"]
    assert plan["must_cite"] is True


def test_query_specific_answer_format():
    from backend.app.prompts.registry import get_query_format
    assert "Variables" in get_query_format("equation")
    assert "Document A" in get_query_format("comparison")
    assert "DERIVED" in get_query_format("calculation")
    assert get_query_format("definition") != get_query_format("procedure")


def test_generation_validation_flag():
    import asyncio
    from backend.app.services.rag import rag_query
    db = SessionLocal()

    async def run():
        off = await rag_query(db, "What equation defines electrical power?", top_k=3,
                              apply_validation=False, answer_length="brief")
        assert "post_generation_validation_disabled(ablation)" in off["validation_actions"]
        on = await rag_query(db, "What equation defines electrical power?", top_k=3,
                             apply_validation=True, answer_length="brief")
        assert "prompt_version" in on and "answer_plan" in on and "token_usage" in on
        return off, on
    off, on = asyncio.run(run())
    assert off["context_mode"] in ("optimized", "flat(fallback)")
    flat = asyncio.run(rag_query(db, "What equation defines electrical power?", top_k=3,
                                 context_mode="flat", answer_length="brief"))
    assert flat["context_mode"] == "flat"


def test_numeric_reasoning_derived():
    # Unit level (deterministic): crafted prompt with P=VI evidence.
    # (End-to-end retrieval order for this query is TFIDF-nondeterministic,
    # so the branch is tested here, not via retrieval luck.)
    import asyncio
    from backend.app.core.llm_provider import MockLLMProvider
    ctx = ("SOURCE 1\nDocument: notes.md\nPage: 1\nSection: Equations\nChunk: c1\n"
           "Content:\nPower: P = V * I defines electrical power.\n---\n")
    prompt = ("Question: Calculate power if V=3.3V and I=1.27A\nQuery Type: calculation\n"
              "Length: brief\n\nCONTEXT:\n" + ctx)

    async def run():
        return await MockLLMProvider().generate(prompt, system="x", temperature=0.2)
    ans = asyncio.run(run())
    assert "DERIVED" in ans
    assert "4.191" in ans  # 3.3*1.27=4.191, SymPy-verified substitution


def test_derived_reasoning_label():
    import asyncio
    from backend.app.services.rag import rag_query
    db = SessionLocal()

    async def run():
        return await rag_query(db, "What happens to P if V doubles while I is constant according to P = VI?",
                               top_k=5, answer_length="brief")
    r = asyncio.run(run())
    assert "DERIVED" in r["answer"]
    assert any(c.get("type") == "derived" for c in r["claims"])


def test_pairwise_blind_hides_systems():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.models.evaluation import EvaluationCase
    db = SessionLocal()
    case = db.query(EvaluationCase).first()
    client = TestClient(app)
    r = client.post("/api/grading/pair", json={"evaluation_case_id": case.id, "seed": 7})
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert "answer_a" in body and "answer_b" in body and "pair_id" in body
    # Blinded: no system names anywhere in the pair payload
    blob = (body["answer_a"] + body["answer_b"]).lower()
    assert "tfidf" not in blob and "dense" not in blob
    # Submit preference without ever seeing mapping
    r2 = client.post("/api/grading/pairwise-blind", json={
        "pair_id": body["pair_id"], "grader_id": "test-blinder",
        "preferred_answer": "tie", "reason": "test"})
    assert r2.status_code == 200
    # Cleanup
    from backend.app.models.pairwise import PairwiseGrade
    db.query(PairwiseGrade).filter(PairwiseGrade.grader_id == "test-blinder").delete()
    db.commit()


def test_pairwise_summary_counts():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)
    r = client.get("/api/grading/pairwise/summary")
    assert r.status_code == 200
    body = r.json()
    total = sum(sum(v.values()) for v in body.values())
    assert total >= 30  # 30 blinded retrieval-contrast grades submitted


def test_grading_progress():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)
    r = client.get("/api/grading/progress")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 100 and body["graded"] == 100 and body["double_graded"] >= 30


def test_metric_v3_unit_cases():
    from backend.app.services.evaluation_v3_helper import (
        compute_answer_relevance_v3, strip_boilerplate)
    # Tolerance: 4.191W satisfies required 4.2W
    r = compute_answer_relevance_v3("P = 4.191 W [SOURCE]", [], ["4.2W"], [], "Calculate power?", [], [])
    assert r["value_coverage"] == 1.0
    # Percent variants
    r = compute_answer_relevance_v3("increased by 14 percent [SOURCE]", [], ["14%"], [], "Q?", [], [])
    assert r["value_coverage"] == 1.0
    # Boilerplate stripped: values only in footer must NOT count
    ans = "Generic text. [SOURCE]\n\n> **Conflict detected [SOURCE]:** power values differ: 4.2W, 3.14W."
    r = compute_answer_relevance_v3(ans, [], ["4.2W"], [], "What power?", [], [])
    assert r["value_coverage"] == 0.0
    assert strip_boilerplate(ans) == "Generic text. [SOURCE]"
    # Directness capped for generic openers
    r = compute_answer_relevance_v3("This paper investigates thermoelectric modules. [SOURCE]", ["Seebeck"], [], [], "What is Seebeck?", [], [])
    assert r["directness_score"] <= 0.5
    assert r["metric_version"] == "v3"


def test_evaluation_reproducibility_metadata():
    import asyncio
    from backend.app.services.rag import rag_query
    db = SessionLocal()

    async def run():
        return await rag_query(db, "What is the Seebeck effect?", top_k=3, answer_length="brief")
    r = asyncio.run(run())
    assert r["prompt_version"] in ("v1", "v2", "v3")
    assert r["answer_plan"]["question_type"] == r["query_type"]
    assert set(r["generation_settings"]) == {"temperature", "top_p", "max_tokens"}
    assert "llm_identity" in r and "requested_llm_provider" in r["llm_identity"]
