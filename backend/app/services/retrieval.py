import re
import math
import numpy as np
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from ..models.chunk import DocumentChunk
from ..models.embedding import Embedding
from ..core.embedding_provider import get_global_embedding_provider
from ..core.reranker import SimpleReranker, get_reranker
from ..config import settings
# v0.2 imports
try:
    from .retrieval_v2 import retrieve_v2, mmr_selection, normalize_scores
except ImportError:
    retrieve_v2 = None  # type: ignore

def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    denom = (np.linalg.norm(a)* np.linalg.norm(b))
    if denom==0:
        return 0.0
    return float(np.dot(a,b)/denom)

def keyword_score(query: str, text: str) -> float:
    """Simple BM25-style keyword scoring: TF * IDF approximation using term overlap and length normalization"""
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
        # idf approx: rare terms higher weight (log)
        # we approximate idf=1 for all; bonus for exact phrase
        tf_norm = tf / (tf + 0.5 + 0.5* len(t_terms)/200)
        score += tf_norm
    # phrase boost
    if query.lower() in text.lower():
        score += 0.5
    # normalize 0-1
    max_possible = len(q_set) + 0.5
    return min(score / max_possible, 1.0) if max_possible else 0

def retrieve(
    db: Session,
    query: str,
    top_k: int = 8,
    filters: Optional[Dict] = None,
    document_ids: Optional[List[str]] = None,
    collection_id: Optional[str] = None,
    use_v2: bool = True,
    with_trace: bool = False,
) -> List[Dict]:
    """
    Hybrid retrieval v0.2 wrapper: delegates to retrieval_v2 when available.
    Preserves v0.1 signature for backward compat; use retrieve_with_trace for full trace.
    """
    if use_v2 and retrieve_v2 is not None:
        try:
            results, trace = retrieve_v2(db, query, top_k=top_k, filters=filters, document_ids=document_ids, collection_id=collection_id, trace=True)
            # attach trace via attribute if requested
            if with_trace:
                # store trace on results object via extra key (first element)
                # caller can call retrieve_with_trace explicitly
                pass
            return results
        except Exception as e:
            import logging
            logging.warning(f"retrieve_v2 failed {e}, falling back to v0.1 retrieval")
    # fallback v0.1 legacy
    filters = filters or {}
    query_clean = query.strip()
    if not query_clean:
        return []
    provider = get_global_embedding_provider()
    query_vec = provider.embed_query(query_clean)
    q = db.query(DocumentChunk, Embedding).join(Embedding, Embedding.chunk_id==DocumentChunk.id)
    if document_ids:
        q = q.filter(DocumentChunk.document_id.in_(document_ids))
    if filters.get("document_id"):
        q = q.filter(DocumentChunk.document_id == filters["document_id"])
    if filters.get("content_type"):
        q = q.filter(DocumentChunk.content_type == filters["content_type"])
    if filters.get("section"):
        q = q.filter(DocumentChunk.section.ilike(f"%{filters['section']}%"))
    if filters.get("page"):
        q = q.filter(DocumentChunk.page_number == filters["page"])
    if collection_id:
        from ..models.collection import CollectionDocument
        doc_ids_in_col = [r.document_id for r in db.query(CollectionDocument).filter(CollectionDocument.collection_id==collection_id).all()]
        if doc_ids_in_col:
            q = q.filter(DocumentChunk.document_id.in_(doc_ids_in_col))
        else:
            return []
    candidates = q.all()
    scored = []
    for chunk, emb in candidates:
        vec = emb.vector if emb and emb.vector else None
        vector_score = cosine_similarity(query_vec, vec) if vec else 0.0
        kw_score = keyword_score(query_clean, chunk.text)
        hybrid = settings.hybrid_vector_weight * vector_score + settings.hybrid_keyword_weight * kw_score
        scored.append({
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "document_name": chunk.document_name,
            "page_number": chunk.page_number,
            "section": chunk.section,
            "heading_hierarchy": chunk.heading_hierarchy,
            "text": chunk.text,
            "content_type": chunk.content_type,
            "vector_score": float(vector_score),
            "keyword_score": float(kw_score),
            "score": float(hybrid),
            "retrieval_score": float(hybrid),
        })
    ranked = sorted(scored, key=lambda x: x["score"], reverse=True)
    filtered = [r for r in ranked if r["score"] >= settings.min_relevance_score]
    if not filtered and ranked:
        filtered = ranked[:3]
    reranker = SimpleReranker()
    reranked = reranker.rerank(query_clean, filtered, top_k=top_k)
    return reranked[:top_k]

def retrieve_with_trace(db: Session, query: str, top_k: int = 8, filters: Optional[Dict] = None, document_ids: Optional[List[str]] = None, collection_id: Optional[str] = None):
    """Explicit v2 trace API"""
    if retrieve_v2 is not None:
        return retrieve_v2(db, query, top_k=top_k, filters=filters, document_ids=document_ids, collection_id=collection_id, trace=True)
    # fallback trace empty
    res = retrieve(db, query, top_k=top_k, filters=filters, document_ids=document_ids, collection_id=collection_id, use_v2=False)
    trace = {"query": query, "retrieval_strategy": "v0.1 fallback", "final_evidence": len(res), "reranker": "simple"}
    return res, trace

def build_rag_context(retrieved: List[Dict]) -> str:
    """Build structured context for LLM"""
    lines = []
    for i, r in enumerate(retrieved, start=1):
        lines.append(f"SOURCE {i}")
        lines.append(f"Document: {r['document_name']}")
        lines.append(f"Page: {r['page_number']}")
        lines.append(f"Section: {r['section']}")
        lines.append(f"Chunk: {r['chunk_id']}")
        lines.append(f"Retrieval Score: {r['retrieval_score']:.3f}")
        lines.append(f"Content Type: {r['content_type']}")
        lines.append("")
        # escape instruction injection: wrap in clear data delimiters
        lines.append("Content:")
        lines.append(r['text'][:1500])
        lines.append("---")
        lines.append("")
    return "\n".join(lines)

def get_evidence_for_claim(claim_text: str, retrieved: List[Dict], threshold: float = 0.15) -> List[Dict]:
    # find which retrieved chunks support claim (overlap)
    evidence=[]
    claim_terms = set(re.findall(r"\w+", claim_text.lower()))
    for r in retrieved:
        text_terms = set(re.findall(r"\w+", r["text"].lower()))
        overlap = len(claim_terms.intersection(text_terms)) / max(len(claim_terms),1)
        if overlap>threshold or r["score"]>0.2:
            evidence.append(r)
    return evidence[:3]
