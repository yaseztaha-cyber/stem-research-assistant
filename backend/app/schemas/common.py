from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class MessageResponse(BaseModel):
    message: str

class PaginatedResponse(BaseModel):
    total: int
    items: List[Any]
