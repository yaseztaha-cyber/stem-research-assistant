from abc import ABC, abstractmethod
from typing import List, Dict

class RerankerProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    @abstractmethod
    def rerank(self, query: str, candidates: List[Dict], top_k: int = 5) -> List[Dict]:
        pass

class SimpleReranker(RerankerProvider):
    """Heuristic reranker: boost exact phrase matches, heading matches, equation content types for relevant queries.
    v0.4: query-type-aware section preferences (methodology/procedure prefer Methods/Procedure over Abstract)."""
    @property
    def name(self) -> str:
        return "simple"
    def rerank(self, query: str, candidates: List[Dict], top_k: int = 5) -> List[Dict]:
        q_low = query.lower()
        q_terms = set(q_low.split())
        # v0.4: classify once for query-type-aware boosts (no LLM)
        try:
            from ..services.query_classifier import classify_query
            qtype = classify_query(query).get("query_type", "general")
        except Exception:
            qtype = "general"
        for c in candidates:
            bonus = 0
            text_low = c.get("text","").lower()
            sec_low = (c.get("section","") or "").lower()
            head_low = (c.get("heading_hierarchy","") or "").lower()
            ctype = c.get("content_type","")
            # phrase match
            if q_low in text_low:
                bonus += 0.15
            # term overlap
            overlap = len(q_terms.intersection(set(text_low.split()))) / max(len(q_terms),1)
            bonus += overlap * 0.1
            # boost definitions/results for "what is" queries
            if "what is" in q_low and ctype in ["definition","paragraph"]:
                bonus += 0.05
            if "equation" in q_low and ctype=="equation":
                bonus += 0.2
            # metadata-aware boosts (legacy terms)
            if "results" in q_low and sec_low.find("result")!=-1:
                bonus += 0.08
            if "method" in q_low and ctype=="procedure":
                bonus += 0.08
            # v0.4 query-type-aware section preferences (modest, validated on full benchmark)
            if qtype in ("methodology", "procedure"):
                if any(s in sec_low for s in ["method", "procedure", "experimental setup", "materials"]) or any(s in head_low for s in ["method", "procedure", "experimental setup", "materials"]):
                    bonus += 0.10
                if ctype == "procedure":
                    bonus += 0.06
                # Demote abstract/introduction for methodology queries (small penalty)
                if any(s in sec_low for s in ["abstract", "introduction"]) and "abstract" not in q_low:
                    bonus -= 0.06
                if any(s in sec_low for s in ["discussion", "conclusion", "references"]):
                    bonus -= 0.03
            elif qtype in ("experimental_result", "table"):
                if any(s in sec_low for s in ["result", "data", "table", "experimental"]) or ctype in ("result", "table"):
                    bonus += 0.10
                if any(s in sec_low for s in ["abstract"]) and qtype == "table":
                    bonus -= 0.04
            elif qtype == "equation":
                if ctype == "equation":
                    bonus += 0.10
                if any(s in sec_low for s in ["theory", "formula"]):
                    bonus += 0.05
            c["rerank_score"] = c.get("score",0) + bonus
            c["rerank_query_type"] = qtype
            c["reranker"] = self.name
        sorted_c = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
        return sorted_c[:top_k]

def get_active_reranker_identity() -> Dict:
    """Explicit requested/active identity for benchmark integrity (v0.4)."""
    from ..config import settings
    requested = settings.reranker_provider.lower()
    # Normalize names
    req_norm = "cross_encoder" if requested in ("cross_encoder","cross-encoder","crossencoder") else "simple"
    try:
        r = get_reranker()
        active_raw = r.name  # may be "cross_encoder" or "simple(fallback)"
        if "cross_encoder" in active_raw and "fallback" not in active_raw:
            active = "cross_encoder"
            fallback = False
        elif "fallback" in active_raw:
            active = "simple"
            fallback = True
        else:
            active = "simple"
            fallback = (req_norm == "cross_encoder")
        model = settings.cross_encoder_model if active == "cross_encoder" else "simple"
    except Exception:
        active = "simple"
        fallback = (req_norm == "cross_encoder")
        model = "simple"
    import logging
    if fallback and req_norm == "cross_encoder":
        logging.warning(f"requested=cross_encoder, active=simple, fallback=true model={settings.cross_encoder_model}")
    return {
        "requested_reranker": req_norm,
        "active_reranker": active,
        "reranker_model": model,
        "fallback": fallback,
    }

class CrossEncoderReranker(RerankerProvider):
    """Cross-encoder reranker using local sentence-transformers. Falls back to Simple if unavailable."""
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None
        self._use_fallback = False
        self._fallback = SimpleReranker()
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(model_name)
        except Exception as e:
            import logging
            logging.warning(f"CrossEncoderReranker: failed to load {model_name}: {e} -- fallback to Simple")
            self._use_fallback = True

    @property
    def name(self) -> str:
        return "cross_encoder" if not self._use_fallback else "simple(fallback)"

    def rerank(self, query: str, candidates: List[Dict], top_k: int = 5) -> List[Dict]:
        if self._use_fallback or self._model is None:
            res = self._fallback.rerank(query, candidates, top_k)
            for r in res:
                r["reranker"] = self.name  # mark fallback
            return res
        # cross encoder scoring
        pairs = [(query, c.get("text","")[:800]) for c in candidates]
        try:
            scores = self._model.predict(pairs)
            for c, s in zip(candidates, scores):
                # combine original hybrid score with cross encoder (weighted)
                base = c.get("score", 0)
                # normalize cross encoder scores to 0-1 via sigmoid-ish? raw scores roughly -5 to 5, convert
                import math
                ce_norm = 1/(1+math.exp(-float(s)))
                c["cross_encoder_score"] = float(s)
                c["cross_encoder_norm"] = ce_norm
                c["rerank_score"] = 0.4*base + 0.6*ce_norm
                c["reranker"] = self.name
        except Exception as e:
            import logging
            logging.warning(f"CrossEncoder rerank failed {e}, fallback")
            return self._fallback.rerank(query, candidates, top_k)
        sorted_c = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
        return sorted_c[:top_k]

_reranker_instance = None
_reranker_key = None

def get_reranker():
    """Cached singleton to avoid reloading transformer weights per query (v0.4 latency fix)."""
    global _reranker_instance, _reranker_key
    from ..config import settings
    prov = settings.reranker_provider.lower()
    model = getattr(settings, "cross_encoder_model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    key = (prov, model)
    if _reranker_instance is not None and _reranker_key == key:
        return _reranker_instance
    if prov in ("cross_encoder","cross-encoder","crossencoder"):
        _reranker_instance = CrossEncoderReranker(model_name=model)
    else:
        _reranker_instance = SimpleReranker()
    _reranker_key = key
    return _reranker_instance

def reset_reranker():
    global _reranker_instance, _reranker_key
    _reranker_instance = None
    _reranker_key = None
