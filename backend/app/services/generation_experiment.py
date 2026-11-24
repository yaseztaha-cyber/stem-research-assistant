"""Controlled generation experiments (v0.5 §4–§5, §9).

The ONLY intentionally changed component between arms is the generation
model: retrieval, evidence, context, citations and verification are shared.
Strict mode never substitutes mock for a requested real provider.
"""
import time
import uuid
from typing import List, Dict, Optional
from sqlalchemy.orm import Session


def check_real_available() -> tuple[bool, str]:
    from ..config import settings
    key = settings.llm_api_key or settings.openai_api_key
    base = settings.llm_base_url
    if key:
        return True, f"API key configured for {base}"
    if "127.0.0.1" in base or "localhost" in base:
        return True, f"local endpoint {base} (reachability checked per request)"
    return False, "no API key and no local endpoint"


def check_local_available() -> tuple[bool, str]:
    try:
        from transformers import AutoTokenizer  # noqa
    except ImportError as e:
        return False, f"transformers not installed: {e}"
    from ..config import settings
    try:
        from transformers import AutoTokenizer as T
        T.from_pretrained(settings.llm_hf_model, local_files_only=True)
        return True, f"{settings.llm_hf_model} cached"
    except Exception as e:
        return False, f"model not cached: {e}"


_active_retrieval_config: tuple = (None, None)

def _set_retrieval_config(emb: str, rerank: str):
    """Apply retrieval config, reloading models only when it actually changes
    (reloading transformer weights per case would dominate benchmark time)."""
    global _active_retrieval_config
    from ..config import settings
    from ..core.embedding_provider import reset_embedding_provider
    from ..core.reranker import reset_reranker
    from .cache import retrieval_cache
    settings.embedding_provider = emb
    settings.reranker_provider = rerank
    if _active_retrieval_config != (emb, rerank):
        reset_embedding_provider()
        reset_reranker()
        _active_retrieval_config = (emb, rerank)
    retrieval_cache.invalidate("retrieval")


async def run_ab_case(db: Session, question: str, retrieval_cfg: Dict,
                      providers: List[str], prompt_version: str = "v3",
                      answer_length: str = "brief", top_k: int = 5,
                      strict: bool = True, required_elements: Optional[List[str]] = None) -> Dict:
    """One question, one retrieval config, N generators on identical evidence."""
    from ..config import settings
    from ..core.llm_provider import (
        MockLLMProvider, OpenAICompatibleProvider, LocalHFProvider,
        RealLLMUnavailable, reset_llm_provider)
    from .retrieval import retrieve_with_trace
    from .context_builder import build_optimized_context, build_rag_context
    from .grounding import verify_claims_pipeline
    from ..prompts.registry import build_prompt_for_version, build_answer_plan

    _set_retrieval_config(retrieval_cfg["embedding"], retrieval_cfg["reranker"])
    retrieved, trace = retrieve_with_trace(db, question, top_k=top_k)
    query_type = trace.get("query_type", "general") if trace else "general"
    try:
        context = build_optimized_context(db, question, query_type, retrieved)
        if not context.strip():
            context = build_rag_context(retrieved)
    except Exception:
        context = build_rag_context(retrieved)
    plan = build_answer_plan(question, query_type, retrieved, required_elements)
    prompt = build_prompt_for_version(prompt_version, question, context, None, True, query_type, answer_length, plan)

    arms = {}
    for prov in providers:
        reset_llm_provider()
        t0 = time.time()
        try:
            if prov == "mock":
                llm = MockLLMProvider()
            elif prov == "real":
                ok, reason = check_real_available()
                if not ok:
                    raise RealLLMUnavailable(f"BENCHMARK FAILED: Real LLM unavailable ({reason}). No score generated.")
                llm = OpenAICompatibleProvider(
                    model=settings.llm_model, api_key=settings.llm_api_key or settings.openai_api_key,
                    base_url=settings.llm_base_url, temperature=settings.llm_temperature,
                    top_p=settings.llm_top_p, max_tokens=settings.llm_max_tokens)
            elif prov == "local":
                ok, reason = check_local_available()
                if not ok and strict:
                    raise RealLLMUnavailable(f"BENCHMARK FAILED: Local HF model unavailable ({reason}). No score generated.")
                llm = LocalHFProvider(model_name=settings.llm_hf_model,
                                      max_new_tokens=settings.llm_hf_max_new_tokens,
                                      temperature=settings.llm_temperature, top_p=settings.llm_top_p)
                if not llm.available:
                    raise RealLLMUnavailable(f"BENCHMARK FAILED: Local HF model failed to load ({settings.llm_hf_model}). No score generated.")
            else:
                raise ValueError(f"unknown provider {prov}")
            from ..prompts.registry import SYSTEM_PROMPT
            answer = await llm.generate(prompt, system=SYSTEM_PROMPT, temperature=settings.llm_temperature)
            latency_ms = int((time.time() - t0) * 1000)
            pipe = verify_claims_pipeline(answer, retrieved)
            arms[prov] = {
                "answer": answer,
                "claims": pipe["claims"],
                "grounding": pipe["grounding"],
                "citations": pipe["citations"],
                "token_usage": dict(getattr(llm, "last_usage", {}) or {}),
                "latency_ms": latency_ms,
                "model": llm.name,
                "fallback": False,
            }
        except RealLLMUnavailable as e:
            arms[prov] = {"error": str(e)[:400], "fallback": False, "model": prov,
                          "note": "strict mode: no mock substitution"}
        except Exception as e:
            arms[prov] = {"error": f"generation failed: {e}"[:400], "fallback": False, "model": prov}
    return {
        "question": question,
        "query_type": query_type,
        "prompt_version": prompt_version,
        "retrieval_config": retrieval_cfg,
        "retrieved": retrieved,
        "context_sent_to_model": context,
        "answer_plan": plan,
        "retrieval_trace": trace,
        "arms": arms,
        "ab_id": str(uuid.uuid4()),
    }


async def run_generation_matrix(db: Session, questions: List[Dict],
                                retrieval_configs: List[Dict], providers: List[str],
                                prompt_version: str = "v3", strict: bool = True) -> Dict:
    """Full matrix: questions × retrieval configs × providers. Slow for local
    models by design (honest latency); callers batch by subset."""
    results = []
    for q in questions:
        for rc in retrieval_configs:
            case = await run_ab_case(
                db, q["question"], rc, providers, prompt_version,
                answer_length="brief", top_k=5, strict=strict,
                required_elements=(q.get("required_concepts") or []) + (q.get("required_values") or []))
            case["category"] = q.get("category")
            case["required_concepts"] = q.get("required_concepts", [])
            case["required_values"] = q.get("required_values", [])
            results.append(case)
    # Restore defaults
    _set_retrieval_config("tfidf", "simple")
    from ..core.llm_provider import reset_llm_provider
    reset_llm_provider()
    return {"prompt_version": prompt_version, "providers": providers,
            "retrieval_configs": retrieval_configs, "cases": results}
