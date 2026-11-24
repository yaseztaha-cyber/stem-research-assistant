from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
import numpy as np

class VectorStore(ABC):
    @abstractmethod
    def upsert(self, chunk_id: str, vector: List[float], metadata: Dict) -> None:
        pass
    @abstractmethod
    def delete(self, chunk_id: str) -> None:
        pass
    @abstractmethod
    def search(self, query_vector: List[float], top_k: int = 10, filters: Optional[Dict] = None) -> List[Tuple[str, float]]:
        """returns list of (chunk_id, score)"""
        pass
    @abstractmethod
    def batch_search(self, query_vectors: List[List[float]], top_k: int = 10) -> List[List[Tuple[str,float]]]:
        pass

class SQLiteVectorStore(VectorStore):
    """Local SQLite/memory vector store using existing embeddings table.
    No external DB required. Supports filtering via metadata on top of search.
    Future Qdrant/PgVector can implement same interface.
    """
    def __init__(self, db_session_factory):
        # factory returns Session
        self.db_factory = db_session_factory
        self._cache: Dict[str, Tuple[List[float], Dict]] = {}

    def upsert(self, chunk_id: str, vector: List[float], metadata: Dict) -> None:
        # Vectors already stored in embeddings table via ingestion; keep cache for fast search
        self._cache[chunk_id] = (vector, metadata)

    def delete(self, chunk_id: str) -> None:
        self._cache.pop(chunk_id, None)

    def search(self, query_vector: List[float], top_k: int = 10, filters: Optional[Dict] = None) -> List[Tuple[str,float]]:
        # If cache empty, load from DB
        if not self._cache:
            try:
                from ..models.embedding import Embedding
                db = self.db_factory()
                rows = db.query(Embedding).all()
                for r in rows:
                    if r.vector:
                        self._cache[r.chunk_id] = (r.vector, {"document_id": r.document_id})
                db.close()
            except Exception:
                pass
        q = np.array(query_vector, dtype=float)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []
        q = q / q_norm
        scored = []
        for cid, (vec, meta) in self._cache.items():
            if filters:
                skip=False
                for k,v in filters.items():
                    if meta.get(k) != v:
                        # allow substring for section/content_type
                        if k in meta and v.lower() not in str(meta[k]).lower():
                            skip=True
                            break
                        elif k not in meta:
                            skip=True
                            break
                if skip:
                    continue
            v = np.array(vec, dtype=float)
            denom = np.linalg.norm(v)
            if denom==0:
                continue
            v = v/denom
            score = float(np.dot(q, v))
            scored.append((cid, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def batch_search(self, query_vectors: List[List[float]], top_k: int = 10) -> List[List[Tuple[str,float]]]:
        return [self.search(qv, top_k) for qv in query_vectors]

    def load_from_db(self, embeddings: List[Dict]):
        """Bulk load for testing"""
        for e in embeddings:
            self._cache[e["chunk_id"]] = (e["vector"], e.get("metadata",{}))

# placeholder for future
class QdrantVectorStore(VectorStore):
    def __init__(self, url: str, collection: str):
        self.url = url
        self.collection = collection
    def upsert(self, chunk_id: str, vector: List[float], metadata: Dict) -> None:
        raise NotImplementedError("QdrantVectorStore not configured - set QDRANT_URL and install qdrant-client")
    def delete(self, chunk_id: str) -> None:
        raise NotImplementedError
    def search(self, query_vector: List[float], top_k: int = 10, filters: Optional[Dict] = None) -> List[Tuple[str,float]]:
        raise NotImplementedError
    def batch_search(self, query_vectors: List[List[float]], top_k: int = 10) -> List[List[Tuple[str,float]]]:
        raise NotImplementedError

def get_vector_store(db_factory=None):
    # default to SQLite store using SessionLocal
    if db_factory is None:
        from ..database import SessionLocal
        db_factory = SessionLocal
    return SQLiteVectorStore(db_factory)
