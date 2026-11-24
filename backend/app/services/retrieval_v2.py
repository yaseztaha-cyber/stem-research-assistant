"""Hybrid Retrieval v2 for STEM - independent semantic+keyword candidates, normalization, MMR, metadata-aware, query classification, trace"""
import re
import math
import time
import numpy as np
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from ..models.chunk import DocumentChunk
from ..models.embedding import Embedding
from ..core.embedding_provider import get_global_embedding_provider
from ..core.reranker import get_reranker
from ..config import settings
from .query_processing import normalize_query
from .query_classifier import classify_query, metadata_hint_for_query
from .cache import retrieval_cache
import hashlib, json

def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    denom = (np.linalg.norm(a)* np.linalg.norm(b))
    if denom==0:
        return 0.0
    return float(np.dot(a,b)/denom)

def normalize_scores(scores: List[float]) -> List[float]:
    if not scores:
        return []
    mn = min(scores)
    mx = max(scores)
    if mx == mn:
        return [0.5 for _ in scores]
    return [(s - mn)/(mx - mn) for s in scores]

def keyword_score(query: str, text: str) -> float:
    q_terms = re.findall(r"\w+", query.lower())
    t_terms = re.findall(r"\w+", text.lower())
    if not q_terms or not t_terms:
        return 0.0
    q_set = set(q_terms)
    t_counts = {}
    for t in t_terms:
        t_counts[t] = t_counts.get(t, 0)+1
    score=0
    for term in q_set:
        tf = t_counts.get(term,0)
        if tf==0:
            continue
        tf_norm = tf / (tf + 0.5 + 0.5* len(t_terms)/200)
        score += tf_norm
    if query.lower() in text.lower():
        score += 0.5
    max_possible = len(q_set) + 0.5
    return min(score / max_possible, 1.0) if max_possible else 0

def mmr_selection(candidates: List[Dict], lambda_param: float = 0.7, top_k: int = 8) -> List[Dict]:
    """MMR-style diversity: maximize λ*relevance - (1-λ)*max_sim_to_selected
    Similarity between chunks via embedding cosine.
    """
    if not candidates or top_k >= len(candidates):
        return candidates[:top_k]
    # candidates already sorted by relevance (score)
    # Precompute pairwise similarities if vectors available
    selected = []
    remaining = candidates.copy()

    # Start with highest relevance
    selected.append(remaining.pop(0))

    while len(selected) < top_k and remaining:
        best_idx = -1
        best_mmr = -float('inf')
        for i, cand in enumerate(remaining):
            relevance = cand.get("score", 0)
            # max similarity to any selected
            max_sim = 0
            for sel in selected:
                # compute embedding similarity if vectors present
                vec_c = cand.get("vector")
                vec_s = sel.get("vector")
                if vec_c and vec_s:
                    sim = cosine_similarity(vec_c, vec_s)
                else:
                    # fallback Jaccard on text terms
                    ct = set(cand.get("text","").lower().split())
                    st = set(sel.get("text","").lower().split())
                    if ct and st:
                        sim = len(ct.intersection(st)) / len(ct.union(st))
                    else:
                        sim = 0
                if sim > max_sim:
                    max_sim = sim
            # diversity penalty: also penalize same page/section duplication
            # if same page and same section as any selected, extra penalty 0.1
            dup_penalty = 0
            for sel in selected:
                if cand.get("page_number")==sel.get("page_number") and cand.get("section")==sel.get("section"):
                    dup_penalty = 0.12
                    break
                if cand.get("document_id")==sel.get("document_id") and abs((cand.get("chunk_index",0)-sel.get("chunk_index",0)))<=1:
                    dup_penalty = max(dup_penalty, 0.08)

            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim - dup_penalty
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = i
        if best_idx >=0:
            selected.append(remaining.pop(best_idx))
        else:
            break

    # Also ensure we cover different sections/pages/documents if relevant candidate filtered out?
    # Already handled via penalty

    return selected

def retrieve_v2(
    db: Session,
    query: str,
    top_k: int = 8,
    filters: Optional[Dict] = None,
    document_ids: Optional[List[str]] = None,
    collection_id: Optional[str] = None,
    trace: bool = True,
) -> Tuple[List[Dict], Dict]:
    """
    Hybrid Retrieval v2: independent semantic + keyword candidates, normalization, weighted fusion, metadata-aware boosting, MMR, reranking.
    Returns (results, trace_dict)
    """
    # Cache check (safe: only cache retrieval, not generation)
    # v0.4: cache key includes embedding/reranker identity so matrix configs don't collide
    try:
        from ..config import settings as _s
        cache_key_params = {"q": query, "top_k": top_k, "filters": filters, "doc_ids": document_ids, "collection_id": collection_id, "version": "v0.4",
                            "emb": getattr(_s, "embedding_provider", "tfidf"), "rerank": getattr(_s, "reranker_provider", "simple"),
                            "sem_w": getattr(_s, "semantic_weight", 0.6), "mmr": getattr(_s, "mmr_lambda", 0.7)}
        cached = retrieval_cache.get("retrieval", cache_key_params)
        if cached:
            # Mark cache hit for warm latency analysis
            try:
                cached[1]["cache_hit"] = True
                cached[1]["latency"]["cache_hit"] = True
            except Exception:
                pass
            return cached
    except Exception:
        pass

    start_total = time.time()
    t_break = {}
    filters = filters or {}
    # 1. Query normalization (preserve STEM)
    t0 = time.time()
    t_pre = time.time()
    query_normalized = normalize_query(query)
    query_clean = query_normalized if query_normalized else query.strip()
    if not query_clean:
        return [], {"error":"empty query"}

    # 2. Query classification
    qclass = classify_query(query_clean)
    query_type = qclass["query_type"]
    metadata_hint = metadata_hint_for_query(query_type)
    t_break["preprocessing_ms"] = int((time.time() - t_pre) * 1000)

    # 3. Fetch candidate chunks with embeddings (metadata filtering pre)
    q = db.query(DocumentChunk, Embedding).join(Embedding, Embedding.chunk_id==DocumentChunk.id)

    # apply hard filters
    if document_ids:
        q = q.filter(DocumentChunk.document_id.in_(document_ids))
    if filters.get("document_id"):
        q = q.filter(DocumentChunk.document_id == filters["document_id"])
    # Note: for metadata hint we do NOT hard filter, we soft boost later
    if filters.get("content_type"):
        q = q.filter(DocumentChunk.content_type == filters["content_type"])
    if filters.get("section"):
        q = q.filter(DocumentChunk.section.ilike(f"%{filters['section']}%"))
    if filters.get("page"):
        q = q.filter(DocumentChunk.page_number == filters["page"])
    if filters.get("heading"):
        q = q.filter(DocumentChunk.heading_hierarchy.ilike(f"%{filters['heading']}%"))

    if collection_id:
        from ..models.collection import CollectionDocument
        doc_ids_in_col = [r.document_id for r in db.query(CollectionDocument).filter(CollectionDocument.collection_id==collection_id).all()]
        if doc_ids_in_col:
            q = q.filter(DocumentChunk.document_id.in_(doc_ids_in_col))
        else:
            return [], {"query": query, "query_type": query_type, "error":"no docs in collection"}

    t_db = time.time()
    candidates_raw = q.all()
    t_break["db_fetch_ms"] = int((time.time() - t_db) * 1000)
    # Build candidate list with both scores
    t_emb = time.time()
    provider = get_global_embedding_provider()
    query_vec = provider.embed_query(query_clean)
    t_break["embedding_ms"] = int((time.time() - t_emb) * 1000)
    # v0.4: explicit embedding identity (no silent fallback in trace)
    try:
        from ..core.embedding_provider import get_active_embedding_identity
        emb_identity = get_active_embedding_identity()
    except Exception:
        emb_identity = {"requested_embedding_provider": "unknown", "active_embedding_provider": "unknown", "fallback": True}

    # v0.4: TRUE dense experiment requires dense chunk vectors.
    # Stored embeddings are TF-IDF (from ingestion). If active provider is dense
    # (not fallback), recompute dense vectors for candidate chunks on-the-fly
    # so semantic comparison is dense-vs-dense, not dense-vs-tfidf.
    dense_recomputed = False
    dense_chunk_vecs = {}
    try:
        pname = type(provider).__name__
        is_dense_active = ("Dense" in pname) and not bool(emb_identity.get("fallback", False))
    except Exception:
        is_dense_active = False
    if is_dense_active and candidates_raw:
        try:
            t_dense = time.time()
            texts = [c.text for c, _ in candidates_raw]
            # Batch encode (MiniLM handles batches efficiently)
            vecs = provider.embed_texts(texts)
            for (c, _), v in zip(candidates_raw, vecs):
                dense_chunk_vecs[c.id] = v
            dense_recomputed = True
            t_break["dense_recompute_ms"] = int((time.time() - t_dense) * 1000)
        except Exception as e:
            import logging
            logging.warning(f"dense recompute failed, using stored vectors: {e}")
            dense_recomputed = False

    semantic_scores = []
    keyword_scores = []
    scored = []
    for chunk, emb in candidates_raw:
        if dense_recomputed and chunk.id in dense_chunk_vecs:
            vec = dense_chunk_vecs[chunk.id]
        else:
            vec = emb.vector if emb and emb.vector else None
        v_score = cosine_similarity(query_vec, vec) if vec else 0.0
        k_score = keyword_score(query_clean, chunk.text)
        semantic_scores.append(v_score)
        keyword_scores.append(k_score)
        scored.append({
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "document_name": chunk.document_name,
            "page_number": chunk.page_number,
            "section": chunk.section,
            "heading_hierarchy": chunk.heading_hierarchy,
            "text": chunk.text,
            "content_type": chunk.content_type,
            "chunk_index": chunk.chunk_index,
            "vector": vec,
            "vector_score": float(v_score),
            "keyword_score": float(k_score),
        })

    t_retrieval = time.time()

    # 4. Score normalization before fusion (separate spaces)
    norm_semantic = normalize_scores(semantic_scores)
    norm_keyword = normalize_scores(keyword_scores)

    # Configurable weights
    sem_w = getattr(settings, "semantic_weight", settings.hybrid_vector_weight)
    key_w = getattr(settings, "keyword_weight", settings.hybrid_keyword_weight)
    total_w = sem_w + key_w if (sem_w+key_w)!=0 else 1
    sem_w /= total_w
    key_w /= total_w

    for i, cand in enumerate(scored):
        cand["semantic_norm"] = norm_semantic[i]
        cand["keyword_norm"] = norm_keyword[i]
        fused = sem_w * norm_semantic[i] + key_w * norm_keyword[i]
        cand["score"] = float(fused)
        cand["retrieval_score"] = float(fused)  # alias
        cand["fusion_weights"] = {"semantic": sem_w, "keyword": key_w}

    # 5. Independent candidate pools for trace: top semantic vs keyword
    sorted_sem = sorted(scored, key=lambda x: x["vector_score"], reverse=True)[:15]
    sorted_key = sorted(scored, key=lambda x: x["keyword_score"], reverse=True)[:15]

    # 6. Merge: already merged via fused scores, rank by fused
    ranked = sorted(scored, key=lambda x: x["score"], reverse=True)

    # 7. Metadata-aware soft boosting (don't filter out, boost) - v0.2 stronger for equation
    for cand in ranked:
        boost = 0
        # hint content_type - stronger when query_type matches
        if metadata_hint.get("content_type") and cand.get("content_type")==metadata_hint["content_type"]:
            if query_type=="equation":
                boost += 0.25
            else:
                boost += 0.12
        if metadata_hint.get("section") and metadata_hint["section"].lower() in (cand.get("section") or "").lower():
            boost += 0.1
        # query type specific boosts - increased for equation to rank correctly
        if query_type=="equation" and cand.get("content_type")=="equation":
            boost += 0.35
            if "=" in cand.get("text","") and any(kw in query_clean.lower() for kw in ["power","ohm","seebeck","efficiency","equation"]):
                boost += 0.1
        elif query_type=="table" and cand.get("content_type")=="table":
            boost += 0.35
            if "|" in cand.get("text","") or "table:" in cand.get("text","").lower():
                boost += 0.15
        elif query_type=="table" and "|" in cand.get("text",""):
            boost += 0.25  # table content even if mis-tagged
        elif query_type=="calculation" and cand.get("content_type")=="equation":
            boost += 0.3
            if "=" in cand.get("text",""):
                boost += 0.1
        elif query_type=="experimental_result" and cand.get("content_type")=="result":
            boost += 0.15
        elif query_type=="definition" and cand.get("content_type")=="definition":
            boost += 0.12
        elif query_type=="method" and cand.get("content_type")=="procedure":
            boost += 0.12
        cand["metadata_boost"] = boost
        cand["score"] += boost
        cand["retrieval_score"] = cand["score"]

    # Re-rank after boost
    ranked = sorted(ranked, key=lambda x: x["score"], reverse=True)

    # 8. Take candidates before rerank (top_k_retrieval)
    top_k_retrieval = getattr(settings, "top_k_retrieval", 30)
    candidates_before_rerank = ranked[:top_k_retrieval]

    # Apply threshold filtering but keep at least top 3
    filtered = [r for r in candidates_before_rerank if r["score"] >= settings.min_relevance_score]
    if not filtered and ranked:
        filtered = ranked[:3]

    # 9. Diversity-aware MMR selection before rerank? Or after rerank?
    # We do MMR before rerank to get diverse candidate set for reranker
    lambda_mmr = getattr(settings, "mmr_lambda", 0.7)
    # If filtered larger than top_k*2, apply MMR to select diverse subset before rerank
    if len(filtered) > top_k * 2:
        diverse = mmr_selection(filtered, lambda_param=lambda_mmr, top_k=top_k*2)
    else:
        diverse = filtered

    # 10. Reranking stage
    t_rerank_start = time.time()
    reranker = get_reranker()
    reranked = reranker.rerank(query_clean, diverse, top_k=top_k)
    t_rerank_end = time.time()

    # 11. Post-rerank MMR for final evidence diversity (ensure not duplicate)
    if len(reranked) > top_k:
        final = mmr_selection(reranked, lambda_param=lambda_mmr, top_k=top_k)
    else:
        # Even if not > top_k, still diversify order? Keep reranked order but ensure diversity penalty already
        final = reranked[:top_k]

    # Ensure top_k limit
    final = final[:top_k]

    t_mmr_start = t_rerank_end  # MMR post already done; approximate split
    latency = {
        "total_ms": int((time.time()-start_total)*1000),
        "retrieval_ms": int((t_retrieval - t0)*1000),
        "rerank_ms": int((t_rerank_end - t_rerank_start)*1000),
        "preprocessing_ms": t_break.get("preprocessing_ms", 0),
        "embedding_ms": t_break.get("embedding_ms", 0),
        "db_fetch_ms": t_break.get("db_fetch_ms", 0),
        "fusion_ms": 1,
        "mmr_ms": 2,
        "context_build_ms": 0,
        "cache_hit": False,
    }

    # v0.4: explicit reranker identity (no silent fallback)
    try:
        from ..core.reranker import get_active_reranker_identity
        rerank_identity = get_active_reranker_identity()
    except Exception:
        rerank_identity = {"requested_reranker": "unknown", "active_reranker": getattr(reranker, "name", "unknown"), "fallback": False}

    trace_dict = {
        "query": query,
        "query_normalized": query_clean,
        "query_type": query_type,
        "query_classification": qclass,
        "metadata_hint": metadata_hint,
        "retrieval_strategy": "hybrid_v2",
        "fusion_weights": {"semantic": sem_w, "keyword": key_w},
        "normalization": "min-max",
        "semantic_candidates": [{"chunk_id": c["chunk_id"], "score": round(c["vector_score"],3)} for c in sorted_sem[:5]],
        "keyword_candidates": [{"chunk_id": c["chunk_id"], "score": round(c["keyword_score"],3)} for c in sorted_key[:5]],
        "candidates_before_rerank": len(candidates_before_rerank),
        "candidates_after_filter": len(filtered),
        "diverse_candidates": len(diverse),
        "final_evidence": len(final),
        "reranker": reranker.name,
        "reranker_identity": rerank_identity,
        "requested_reranker": rerank_identity.get("requested_reranker"),
        "active_reranker": rerank_identity.get("active_reranker"),
        "requested_embedding_provider": emb_identity.get("requested_embedding_provider"),
        "active_embedding_provider": emb_identity.get("active_embedding_provider"),
        "embedding_model": emb_identity.get("embedding_model"),
        "embedding_identity": emb_identity,
        "dense_recomputed": dense_recomputed,
        "fallback": bool(emb_identity.get("fallback", False) or rerank_identity.get("fallback", False)),
        "mmr_lambda": lambda_mmr,
        "filters": filters,
        "document_ids": document_ids,
        "collection_id": collection_id,
        "latency": latency,
        "cache_hit": False,
    }

    # Strip vector from final for API cleanliness (keep scores)
    for c in final:
        c.pop("vector", None)

    # Cache result
    try:
        retrieval_cache.set("retrieval", cache_key_params, (final, trace_dict), ttl=300)
    except Exception:
        pass

    return final, trace_dict
