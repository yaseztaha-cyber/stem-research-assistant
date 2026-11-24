from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class RagQueryIn(BaseModel):
    query: str
    top_k: Optional[int] = 8
    document_ids: Optional[List[str]] = None
    collection_id: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    grounded_mode: bool = True
    conversation_id: Optional[str] = None

class RagQueryOut(BaseModel):
    answer: str
    retrieved: List[Dict[str, Any]]
    claims: List[Dict[str, Any]]
    grounding: Dict[str, Any]
    citations: List[Dict[str, Any]]
    model: str
    latency: Dict[str, Any]
    request_id: str
    conflict_note: Optional[str] = None
    retrieval_trace: Optional[Dict[str, Any]] = None
    query_type: Optional[str] = None
    citations_v2: Optional[Dict[str, Any]] = None
    contradiction_info: Optional[Dict[str, Any]] = None

class ExplainIn(BaseModel):
    concept: str
    level: str = "intermediate"
    document_ids: Optional[List[str]] = None
    collection_id: Optional[str] = None
