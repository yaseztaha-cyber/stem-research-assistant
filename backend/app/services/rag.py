from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from .retrieval import retrieve, retrieve_with_trace, build_rag_context
from .grounding import extract_claims, evaluate_grounding, hallucination_checks, verify_claims_pipeline, verify_citations_v2, verify_numeric_claim, verify_equation_claim, verify_causal_claim, detect_causal_claim, classify_claim_type
from ..core.llm_provider import get_global_llm, get_active_llm_identity
from ..config import settings
import time
import uuid
import re

# Prompt registry lives in backend/app/prompts/ (v0.5 §41). These aliases keep
# backward compatibility for existing callers/tests.
from ..prompts.registry import (
    SYSTEM_PROMPT,
    get_query_format,
    build_answer_plan,
    build_prompt_for_version,
    PROMPT_VERSIONS,
    DEFAULT_PROMPT_VERSION,
)


def build_prompt(query: str, context: str, chat_history: Optional[List[Dict]] = None, grounded_mode: bool = True, query_type: str = "general", answer_length: str = "standard",
                 prompt_version: str = "v2", answer_plan: Optional[Dict] = None) -> str:
    """Legacy wrapper — defaults to v2 (the v0.3 prompt) for reproducibility."""
    return build_prompt_for_version(prompt_version, query, context, chat_history, grounded_mode, query_type, answer_length, answer_plan)

def detect_contradiction(retrieved: List[Dict]) -> Dict:
    """Detect conflicting values across sources for same metric"""
    # collect numeric values by context (efficiency, power, etc)
    conflicts = []
    # efficiency
    eff_sources = []
    for r in retrieved:
        for m in re.finditer(r"(\d+\.?\d*)\s*%\s*(?:efficiency)?|efficiency\s*[=:]\s*(\d+\.?\d*)\s*%", r["text"], re.IGNORECASE):
            val = m.group(1) or m.group(2)
            if val:
                try:
                    eff_sources.append((float(val), r["document_name"], r["page_number"], r["text"][:120]))
                except: pass
    if len(set([v for v,_,_,_ in eff_sources]))>1:
        # check spread > 2%
        vals = [v for v,_,_,_ in eff_sources]
        if max(vals)-min(vals) > 2:
            conflicts.append({"metric": "efficiency", "values": eff_sources, "type": "numerical_conflict"})
    # power
    power_sources = []
    for r in retrieved:
        for m in re.finditer(r"(\d+\.?\d*)\s*W\b", r["text"]):
            try:
                power_sources.append((float(m.group(1)), r["document_name"], r["page_number"]))
            except: pass
    if len(power_sources)>=2:
        vals = [v for v,_,_ in power_sources]
        if max(vals)-min(vals) > 1 and len(set(vals))>1:
            # check if same DeltaT but diff power
            conflicts.append({"metric": "power", "values": power_sources, "type": "numerical_conflict"})
    return {"has_conflict": len(conflicts)>0, "conflicts": conflicts}

async def rag_query(
    db: Session,
    query: str,
    top_k: int = 8,
    document_ids: Optional[List[str]] = None,
    collection_id: Optional[str] = None,
    filters: Optional[Dict] = None,
    grounded_mode: bool = True,
    conversation_history: Optional[List[Dict]] = None,
    answer_length: str = "standard",
    required_elements: Optional[List[str]] = None,
    prompt_version: Optional[str] = None,
    llm: Optional[Any] = None,
    context_mode: str = "optimized",  # optimized | flat (v0.5 ablation)
    apply_validation: bool = True,  # v0.5 ablation: post-generation annotation on/off
) -> Dict:
    # 1. Retrieve evidence (v0.2 hybrid with trace)
    start = time.time()
    retrieved, trace = retrieve_with_trace(db, query, top_k=top_k, filters=filters, document_ids=document_ids, collection_id=collection_id)
    retrieval_latency = trace.get("latency", {}).get("total_ms", int((time.time()-start)*1000)) if trace else int((time.time()-start)*1000)
    query_type = trace.get("query_type", "general") if trace else "general"

    # Evidence sufficiency check (v0.3)
    try:
        from .evidence_sufficiency import assess_evidence_sufficiency
        suff = assess_evidence_sufficiency(query, query_type, retrieved)
    except Exception:
        suff = {"status": "sufficient"}

    if not retrieved or suff["status"] == "insufficient":
        # Still proceed but note insufficient
        pass
    if not retrieved:
        return {
            "answer": "No reliable evidence was found in the selected sources. [GENERATED]\n\nThe supplied sources do not provide enough evidence to answer this confidently. Try broadening your document scope or rephrasing the query.",
            "retrieved": [],
            "claims": [],
            "grounding": {"score": 0.0, "percentage": 0, "factors": {"retrieval_relevance":0}, "explanation": "No evidence retrieved"},
            "citations": [],
            "grounded_mode": grounded_mode,
            "model": get_global_llm().name,
            "latency": {"retrieval_ms": retrieval_latency, "llm_ms": 0},
            "retrieval_trace": trace,
            "query_type": query_type,
            "evidence_sufficiency": suff,
            "context_sent_to_model": "",
        }

    # 2. Verify evidence exists (already done via retrieval) — suff already
    # 3. Context construction (optimized = source-aware expansion/grouping; flat = plain top-k for ablation)
    context_mode_used = context_mode
    try:
        from .context_builder import build_optimized_context
        if context_mode == "flat":
            context = build_rag_context(retrieved)
        else:
            context = build_optimized_context(db, query, query_type, retrieved)
            # Fallback if empty
            if not context.strip():
                context = build_rag_context(retrieved)
                context_mode_used = "flat(fallback)"
    except Exception as e:
        context = build_rag_context(retrieved)
        context_mode_used = "flat(fallback)"

    # 3b. Answer plan (v0.5 §17, internal; developer mode only)
    prompt_version = prompt_version or getattr(settings, "answer_prompt_version", DEFAULT_PROMPT_VERSION)
    try:
        answer_plan = build_answer_plan(query, query_type, retrieved, required_elements)
    except Exception:
        answer_plan = {"question_type": query_type, "required_elements": [], "evidence_ids": [], "must_cite": True}

    # Build prompt with query_type and length control (versioned registry)
    prompt = build_prompt(query, context, conversation_history, grounded_mode, query_type=query_type, answer_length=answer_length,
                          prompt_version=prompt_version, answer_plan=answer_plan)

    # 4. Generate answer (injectable llm enables controlled A/B on identical evidence)
    if llm is None:
        llm = get_global_llm()
    llm_start = time.time()
    validation_actions: List[str] = []
    try:
        answer = await llm.generate(prompt, system=SYSTEM_PROMPT, temperature=settings.llm_temperature)
    except Exception as e:
        answer = f"AI provider unavailable. Your documents are still available locally. [GENERATED]\n\nError: {str(e)[:300]} \n\nRetrieved evidence (without AI generation):\n" + "\n".join([f"- {r['document_name']} p.{r['page_number']}: {r['text'][:200]}" for r in retrieved[:3]])
        validation_actions.append(f"generation_failed_fallback_to_evidence_list: {str(e)[:100]}")
    llm_latency = int((time.time()-llm_start)*1000)
    # Token/cost tracking when the provider reports usage (v0.5 §8; never logged keys)
    token_usage = dict(getattr(llm, "last_usage", {}) or {})
    try:
        llm_identity = get_active_llm_identity()
    except Exception:
        llm_identity = {"requested_llm_provider": "unknown", "active_llm_provider": getattr(llm, "name", "unknown")}

    # 5. Claim extraction
    claims_raw = extract_claims(answer)

    # 6. Claim ↔ evidence matching + verification pipeline (v0.2)
    pipeline = verify_claims_pipeline(answer, retrieved)
    claims_verified = pipeline["claims"]
    grounding = pipeline["grounding"]
    citations_v2 = pipeline["citations"]
    hallucination = pipeline["hallucination"]

    # 7. Citation validation (v0.2) - attach per-citation status
    # citations_v2 already validated; build provenance citations with validation
    citations = []
    for r in retrieved:
        citations.append({
            "type": "source",
            "document": r["document_name"],
            "document_id": r["document_id"],
            "page": r["page_number"],
            "section": r["section"],
            "chunk_id": r["chunk_id"],
            "source_text": r["text"][:500],
            "retrieval_score": r["retrieval_score"],
            "citation_metadata": {"heading_hierarchy": r["heading_hierarchy"], "content_type": r["content_type"]},
            "validation": "VALID",  # since retrieved directly, treat as valid provenance
        })

    # 8. Remove or relabel unsupported claims in grounded mode (policy hierarchy)
    # Instead of mutating answer string heavily, we annotate and add disclaimer
    # If causal claim overstates correlation, append correction
    causal_corrections = []
    for c in claims_verified:
        if c.get("claim_type")=="causal_claim" and c.get("support_status")=="unsupported":
            causal_info = verify_causal_claim(c["text"], retrieved)
            if "corrected" in causal_info:
                causal_corrections.append(causal_info["corrected"])
    if not apply_validation:
        validation_actions.append("post_generation_validation_disabled(ablation)")
    if causal_corrections and grounded_mode and apply_validation:
        answer += "\n\n> **Causal claim note [GENERATED correction]:** " + " ".join(set(causal_corrections)) + " [GENERATED]"
        validation_actions.append(f"causal_overstatement_labeled: {len(causal_corrections)} claim(s)")

    # If unsupported rate high, relabel and warn
    if grounded_mode and hallucination["unsupported_rate"] > 0.4 and apply_validation:
        answer += "\n\n> ⚠️ The supplied sources do not provide enough evidence to fully support all claims above. Unsupported claims have been flagged as [GENERATED] or should be verified."
        validation_actions.append(f"unsupported_rate_{hallucination['unsupported_rate']:.2f}_disclaimer_added")
    # If any claim marked contradicted, note
    contradicted = [c for c in claims_verified if c.get("support_status")=="contradicted"]
    if contradicted and grounded_mode and apply_validation:
        answer += "\n\n> ⚠️ Contradiction detected: claimed value conflicts with source evidence; see verification details."
        validation_actions.append(f"contradicted_claims_flagged: {len(contradicted)}")

    # 9. Contradiction detection across sources
    contradiction_info = detect_contradiction(retrieved)
    conflict_note = None
    if contradiction_info["has_conflict"]:
        # Build explicit conflict answer addition if not already stated
        conflict_note = "The sources report different values for the same metric; see conflicts below."
        if grounded_mode and "disagree" not in answer.lower():
            # Append conflict summary
            parts = []
            for conf in contradiction_info["conflicts"]:
                vals_str = ", ".join([f"{v}% ({doc} p.{pg})" for v,doc,pg,_ in conf["values"][:2]] if conf["metric"]=="efficiency" else [f"{v}W" for v,_,_ in conf["values"][:2]])
                parts.append(f"{conf['metric']} values differ: {vals_str}")
            if parts:
                answer += f"\n\n> **Conflict detected [SOURCE]:** {'; '.join(parts)}. The sources therefore disagree on this point. [SOURCE]"

    # Update grounding contradiction factor based on detection
    if contradiction_info["has_conflict"] and "disagree" in answer.lower():
        # contradiction handled
        grounding["factors"]["contradiction_handled"] = 0.9
    elif contradiction_info["has_conflict"]:
        grounding["factors"]["contradiction_handled"] = 0.6
        grounding["score"] = max(0, grounding["score"] - 0.05)

    # Attach per-claim evidence already in pipeline
    claims_with_evidence = claims_verified
    # Build claim_evidence_links
    claim_evidence_links = [{"claim": c["text"], "evidence_ids": c.get("evidence_ids", []), "support_status": c.get("support_status"), "citation_status": c.get("citation_status")} for c in claims_with_evidence]

    # Evidence quality: sufficiency already computed
    evidence_quality = suff

    # Answer relevance v2 placeholder (computed in evaluation, here simple)
    # For traceability, store all layers
    return {
        "answer": answer,
        "generated_answer": answer,
        "retrieved": retrieved,
        "selected_evidence": retrieved,
        "retrieved_candidates": trace.get("candidates_before_rerank", 0),
        "reranked_candidates": trace.get("final_evidence", len(retrieved)),
        "claims": claims_with_evidence,
        "claim_evidence_links": claim_evidence_links,
        "citation_validation": citations_v2,
        "grounding": grounding,
        "citations": citations,
        "citations_v2": citations_v2,
        "grounded_mode": grounded_mode,
        "model": llm.name,
        "latency": {"retrieval_ms": retrieval_latency, "llm_ms": llm_latency, "rerank_ms": trace.get("latency",{}).get("rerank_ms",0) if trace else 0, "total_ms": retrieval_latency + llm_latency},
        "conflict_note": conflict_note,
        "contradiction_info": contradiction_info,
        "hallucination_checks": hallucination,
        "retrieval_trace": trace,
        "query_type": query_type,
        "evidence_sufficiency": evidence_quality,
        "context_sent_to_model": context,
        "answer_length": answer_length,
        "prompt_version": prompt_version,
        "context_mode": context_mode_used,
        "apply_validation": apply_validation,
        "answer_plan": answer_plan,
        "llm_identity": llm_identity,
        "token_usage": token_usage,
        "validation_actions": validation_actions,
        "generation_settings": {"temperature": settings.llm_temperature, "top_p": settings.llm_top_p,
                                "max_tokens": settings.llm_max_tokens},
        "request_id": str(uuid.uuid4())
    }

# Multi-document comparison helper v0.2 with grouped evidence and conflict detection
async def compare_documents(db: Session, query: str, document_ids: List[str]):
    """Creates Paper A evidence vs Paper B evidence comparison with structured grouping"""
    per_doc_results = []
    for doc_id in document_ids:
        res = await rag_query(db, query, document_ids=[doc_id], top_k=4, grounded_mode=True)
        per_doc_results.append({"document_id": doc_id, "answer": res["answer"], "retrieved": res["retrieved"], "grounding": res["grounding"], "citations": res.get("citations", [])})

    # Detect similarities/differences/conflicts
    # Simple: term overlap between per-doc top evidence
    similarities = []
    differences = []
    conflicts = []

    # Collect all retrieved texts per doc
    doc_texts = [" ".join([r["text"] for r in p["retrieved"]]).lower() for p in per_doc_results]
    if len(doc_texts)>=2:
        # Find common terms
        terms_per_doc = [set(t.split()) for t in doc_texts]
        common = set.intersection(*terms_per_doc) if terms_per_doc else set()
        # filter common to meaningful (len>4, not stopwords)
        meaningful = {t for t in common if len(t)>4 and t not in {"about","which","their","there"}}
        if meaningful:
            similarities.append(f"Both sources discuss: {', '.join(list(meaningful)[:5])} [SOURCE]")
        # Differences: terms unique to each
        for i, terms in enumerate(terms_per_doc):
            others = set().union(*[t for j,t in enumerate(terms_per_doc) if j!=i])
            unique = terms - others
            meaningful_unique = {t for t in unique if len(t)>5}
            if meaningful_unique:
                differences.append(f"Document {i+1} uniquely mentions: {', '.join(list(meaningful_unique)[:3])} [SOURCE]")

        # Conflict detection: conflicting numeric values for same metric
        all_retrieved = []
        for p in per_doc_results:
            all_retrieved.extend(p["retrieved"])
        contr = detect_contradiction(all_retrieved)
        if contr["has_conflict"]:
            conflicts = contr["conflicts"]

    # LLM comparison answer
    comparison_context = ""
    for idx, r in enumerate(per_doc_results):
        comparison_context += f"\nDocument {idx+1} ({r['document_id']}) evidence:\n"
        for ev in r["retrieved"][:2]:
            comparison_context += f"- {ev['document_name']} p.{ev['page_number']}: {ev['text'][:300]}\n"
    prompt = f"Compare the following sources regarding query: '{query}'\n{comparison_context}\nProvide: Paper A evidence, Paper B evidence, Comparison, AI interpretation labeled, and note disagreements. Be explicit about conflicts."
    llm = get_global_llm()
    comp_answer = await llm.generate(prompt, system=SYSTEM_PROMPT)

    # Build structured grouping per spec
    grouped = {
        "document_evidence": [
            {"document_id": per_doc_results[i]["document_id"], "supporting_evidence": per_doc_results[i]["retrieved"][:3], "citations": per_doc_results[i].get("citations",[])[:2]}
            for i in range(len(per_doc_results))
        ],
        "comparison": {
            "similarities": similarities,
            "differences": differences,
            "conflicts": conflicts,
            "llm_summary": comp_answer
        }
    }

    return {"per_document": per_doc_results, "comparison": comp_answer, "grouped": grouped, "similarities": similarities, "differences": differences, "conflicts": conflicts}
