from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class DocumentOut(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    status: str
    page_count: int
    doc_metadata: Optional[Dict] = None
    source_quality: str
    error_message: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class DocumentPageOut(BaseModel):
    id: str
    page_number: int
    text: Optional[str]
    char_count: int
    class Config:
        from_attributes = True

class ChunkOut(BaseModel):
    id: str
    document_id: str
    document_name: str
    page_number: Optional[int]
    section: Optional[str]
    heading_hierarchy: Optional[str]
    chunk_index: int
    text: str
    content_type: str
    token_count: int
    class Config:
        from_attributes = True

class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = None

class CollectionOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: datetime
    document_ids: List[str] = []
    class Config:
        from_attributes = True
