from abc import ABC, abstractmethod
from typing import List, Dict
import numpy as np

class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        pass
    @abstractmethod
    def embed_query(self, query: str) -> List[float]:
        pass
    @property
    @abstractmethod
    def dim(self) -> int:
        pass

class TfidfEmbeddingProvider(EmbeddingProvider):
    """Local TF-IDF embedding provider. Fits on corpus and transforms incremental chunks.
    For true incremental, we refit on all known chunks when needed. Simple but works offline.
    """
    def __init__(self, max_features: int = 384):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.max_features = max_features
        self.vectorizer = TfidfVectorizer(max_features=max_features, stop_words='english', ngram_range=(1,2))
        self._fitted = False
        self._corpus: list[str] = []

    def _ensure_fitted(self, texts: List[str]):
        # Fit if not fitted or corpus changed significantly
        combined = self._corpus + texts
        # only refit if new texts add vocabulary
        if not self._fitted:
            self.vectorizer.fit(combined if combined else ["dummy"])
            self._fitted = True
            self._corpus = combined
        else:
            # heuristic: refit if any new text contains unseen bigram? simple: refit if new texts not subset
            new_unique = [t for t in texts if t not in self._corpus]
            if new_unique:
                self._corpus.extend(new_unique)
                # refit
                try:
                    self.vectorizer.fit(self._corpus)
                except Exception:
                    pass

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        self._ensure_fitted(texts)
        vecs = self.vectorizer.transform(texts).toarray()
        # L2 normalize
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms==0]=1
        vecs = vecs / norms
        return vecs.tolist()

    def embed_query(self, query: str) -> List[float]:
        if not self._fitted:
            # fit on query alone
            self.vectorizer.fit([query, "dummy corpus for fitting"])
            self._fitted = True
        vec = self.vectorizer.transform([query]).toarray()[0]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        # pad or truncate to dim
        if len(vec) < self.max_features:
            vec = np.pad(vec, (0, self.max_features - len(vec)))
        elif len(vec) > self.max_features:
            vec = vec[:self.max_features]
        return vec.tolist()

    @property
    def dim(self) -> int:
        return self.max_features

class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.api_key = api_key
        self.model = model
        self._dim = 1536 if "small" in model else 1536

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        import httpx
        headers = {"Authorization": f"Bearer {self.api_key}"}
        vectors = []
        for text in texts:
            resp = httpx.post("https://api.openai.com/v1/embeddings", headers=headers, json={"input": text, "model": self.model}, timeout=20)
            resp.raise_for_status()
            vectors.append(resp.json()["data"][0]["embedding"])
        return vectors

    def embed_query(self, query: str) -> List[float]:
        return self.embed_texts([query])[0]

    @property
    def dim(self) -> int:
        return self._dim

class DenseEmbeddingProvider(EmbeddingProvider):
    """Local dense embedding via sentence-transformers (e.g., all-MiniLM-L6-v2).
    Works offline after first download; falls back to TF-IDF if model unavailable.
    """
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", max_features: int = 384):
        self.model_name = model_name
        self._dim = max_features
        self._model = None
        self._fallback = TfidfEmbeddingProvider(max_features=max_features)
        self._use_fallback = False
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
            self._dim = self._model.get_sentence_embedding_dimension() or max_features
            # warmup
        except Exception as e:
            import logging
            logging.warning(f"DenseEmbeddingProvider: failed to load {model_name}: {e} — falling back to TF-IDF")
            self._use_fallback = True

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if self._use_fallback or self._model is None:
            return self._fallback.embed_texts(texts)
        import numpy as np
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        # ensure list
        if hasattr(vecs, 'tolist'):
            return vecs.tolist()
        return [list(v) for v in vecs]

    def embed_query(self, query: str) -> List[float]:
        if self._use_fallback or self._model is None:
            return self._fallback.embed_query(query)
        vec = self._model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
        if hasattr(vec, 'tolist'):
            return vec.tolist()
        return list(vec)

    @property
    def dim(self) -> int:
        return self._dim

def get_embedding_provider():
    from ..config import settings
    import logging
    prov = settings.embedding_provider.lower()
    if prov == "openai" and settings.openai_api_key:
        return OpenAIEmbeddingProvider(settings.openai_api_key, settings.openai_embedding_model)
    if prov in ("dense", "sentence_transformer", "sentence-transformer", "local"):
        p = DenseEmbeddingProvider(model_name=settings.dense_embedding_model)
        # Production fallback logging with explicit identity (v0.4 integrity)
        if getattr(p, "_use_fallback", False):
            logging.warning(f"requested=dense, active=tfidf, fallback=true model={settings.dense_embedding_model} reason=sentence-transformers unavailable")
        else:
            logging.info(f"requested=dense, active=dense, fallback=false model={settings.dense_embedding_model}")
        return p
    # default tfidf - preserves v0.1 fallback without external infra
    return TfidfEmbeddingProvider()

def get_active_embedding_identity() -> Dict:
    """Return explicit requested/active identity for benchmark integrity (v0.4)."""
    from ..config import settings
    requested = settings.embedding_provider.lower()
    provider = get_global_embedding_provider()
    t = type(provider).__name__
    if "Dense" in t:
        active = "dense" if not getattr(provider, "_use_fallback", False) else "tfidf"
        fallback = bool(getattr(provider, "_use_fallback", False))
        model = getattr(provider, "model_name", settings.dense_embedding_model)
    elif "OpenAI" in t:
        active = "openai"
        fallback = False
        model = getattr(provider, "model", settings.openai_embedding_model)
    else:
        active = "tfidf"
        # If requested dense but active tfidf, that's fallback
        fallback = (requested == "dense")
        model = "tfidf"
    return {
        "requested_embedding_provider": requested,
        "active_embedding_provider": active,
        "embedding_model": model,
        "fallback": fallback,
    }

# singleton
_provider_instance = None
def get_global_embedding_provider():
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = get_embedding_provider()
    return _provider_instance

def reset_embedding_provider():
    global _provider_instance
    _provider_instance = None
