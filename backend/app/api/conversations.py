from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from ..database import get_db
from ..models.conversation import Conversation, Message

router = APIRouter(prefix="/conversations", tags=["conversations"])

class CreateConv(BaseModel):
    title: Optional[str] = None
    collection_id: Optional[str] = None
    document_ids: Optional[List[str]] = None

@router.post("")
def create_conversation(body: CreateConv, db: Session = Depends(get_db)):
    conv = Conversation(title=body.title or "Research Workspace", collection_id=body.collection_id, document_ids=body.document_ids)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"id": conv.id, "title": conv.title, "collection_id": conv.collection_id, "document_ids": conv.document_ids, "created_at": conv.created_at}

@router.get("")
def list_conversations(db: Session = Depends(get_db)):
    convs = db.query(Conversation).order_by(Conversation.created_at.desc()).all()
    return [{"id": c.id, "title": c.title, "collection_id": c.collection_id, "document_ids": c.document_ids, "created_at": c.created_at, "message_count": len(c.messages)} for c in convs]

@router.get("/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id==conversation_id).first()
    if not conv:
        raise HTTPException(404, "Not found")
    msgs = [{"id": m.id, "role": m.role, "content": m.content, "grounding_score": m.grounding_score, "citations": m.citations, "created_at": m.created_at} for m in conv.messages]
    return {"id": conv.id, "title": conv.title, "collection_id": conv.collection_id, "document_ids": conv.document_ids, "created_at": conv.created_at, "messages": msgs}

@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id==conversation_id).first()
    if not conv:
        raise HTTPException(404, "Not found")
    db.delete(conv)
    db.commit()
    return {"message": "deleted"}
