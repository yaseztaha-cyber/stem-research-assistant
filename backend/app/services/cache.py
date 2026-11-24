import time
from typing import Dict, Any, Callable
import hashlib
import json

class SimpleCache:
    def __init__(self, default_ttl: int = 300):
        self.store: Dict[str, tuple[Any, float]] = {}
        self.ttl = default_ttl

    def _key(self, namespace: str, params: dict) -> str:
        # deterministic key
        s = json.dumps(params, sort_keys=True, default=str)
        h = hashlib.md5(s.encode()).hexdigest()
        return f"{namespace}:{h}"

    def get(self, namespace: str, params: dict):
        k = self._key(namespace, params)
        if k in self.store:
            val, exp = self.store[k]
            if time.time() < exp:
                return val
            else:
                del self.store[k]
        return None

    def set(self, namespace: str, params: dict, value: Any, ttl: int = None):
        k = self._key(namespace, params)
        exp = time.time() + (ttl if ttl is not None else self.ttl)
        self.store[k] = (value, exp)

    def invalidate(self, namespace: str = None):
        if namespace is None:
            self.store.clear()
        else:
            keys = [k for k in self.store if k.startswith(namespace+":")]
            for k in keys:
                del self.store[k]

# Global caches
document_cache = SimpleCache(default_ttl=3600)
embedding_cache = SimpleCache(default_ttl=3600)
retrieval_cache = SimpleCache(default_ttl=600)
evaluation_cache = SimpleCache(default_ttl=300)

def cached(namespace: str, ttl: int = 300):
    cache = {
        "document": document_cache,
        "embedding": embedding_cache,
        "retrieval": retrieval_cache,
        "evaluation": evaluation_cache,
    }.get(namespace, SimpleCache(ttl))
    def decorator(fn: Callable):
        def wrapper(*args, **kwargs):
            # Try to create key from args that are hashable; fallback to no cache if complex
            try:
                # For functions with db Session, we cannot hash db; skip cache for those with Session
                has_session = any(hasattr(a, 'query') for a in args)
                if has_session:
                    return fn(*args, **kwargs)
                params = {"args": args, "kwargs": kwargs}
                cached_val = cache.get(namespace, params)
                if cached_val is not None:
                    return cached_val
                res = fn(*args, **kwargs)
                cache.set(namespace, params, res, ttl=ttl)
                return res
            except Exception:
                return fn(*args, **kwargs)
        return wrapper
    return decorator
