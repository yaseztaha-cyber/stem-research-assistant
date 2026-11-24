from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.collection import Collection, CollectionDocument
from ..schemas.document import CollectionCreate, CollectionOut

router = APIRouter(prefix="/collections", tags=["collections"])

@router.post("", response_model=CollectionOut)
def create_collection(body: CollectionCreate, db: Session = Depends(get_db)):
    c = Collection(name=body.name, description=body.description)
    db.add(c)
    db.commit()
    db.refresh(c)
    return CollectionOut(id=c.id, name=c.name, description=c.description, created_at=c.created_at, document_ids=[])

@router.get("", response_model=list[CollectionOut])
def list_collections(db: Session = Depends(get_db)):
    cols = db.query(Collection).all()
    out=[]
    for c in cols:
        doc_ids = [r.document_id for r in db.query(CollectionDocument).filter(CollectionDocument.collection_id==c.id).all()]
        out.append(CollectionOut(id=c.id, name=c.name, description=c.description, created_at=c.created_at, document_ids=doc_ids))
    return out

@router.get("/{collection_id}", response_model=CollectionOut)
def get_collection(collection_id: str, db: Session = Depends(get_db)):
    c = db.query(Collection).filter(Collection.id==collection_id).first()
    if not c:
        raise HTTPException(404, "Not found")
    doc_ids = [r.document_id for r in db.query(CollectionDocument).filter(CollectionDocument.collection_id==c.id).all()]
    return CollectionOut(id=c.id, name=c.name, description=c.description, created_at=c.created_at, document_ids=doc_ids)

@router.post("/{collection_id}/documents/{document_id}")
def add_document(collection_id: str, document_id: str, db: Session = Depends(get_db)):
    c = db.query(Collection).filter(Collection.id==collection_id).first()
    if not c:
        raise HTTPException(404, "Collection not found")
    exists = db.query(CollectionDocument).filter(CollectionDocument.collection_id==collection_id, CollectionDocument.document_id==document_id).first()
    if exists:
        return {"message": "already added"}
    cd = CollectionDocument(collection_id=collection_id, document_id=document_id)
    db.add(cd)
    db.commit()
    return {"message": "added"}

@router.delete("/{collection_id}/documents/{document_id}")
def remove_document(collection_id: str, document_id: str, db: Session = Depends(get_db)):
    cd = db.query(CollectionDocument).filter(CollectionDocument.collection_id==collection_id, CollectionDocument.document_id==document_id).first()
    if not cd:
        raise HTTPException(404, "Not found")
    db.delete(cd)
    db.commit()
    return {"message": "removed"}

@router.delete("/{collection_id}")
def delete_collection(collection_id: str, db: Session = Depends(get_db)):
    c = db.query(Collection).filter(Collection.id==collection_id).first()
    if not c:
        raise HTTPException(404, "Not found")
    db.delete(c)
    db.commit()
    return {"message": "deleted"}
