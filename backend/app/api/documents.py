from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from pathlib import Path
import shutil

from ..database import get_db
from ..models.document import Document
from ..models.chunk import DocumentChunk
from ..models.equation import Equation
from ..config import settings
from ..core.security import validate_file_size, get_safe_path
from ..services.ingestion import ingest_document
from ..services.dataset import analyze_dataset
from ..schemas.document import DocumentOut, ChunkOut

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=DocumentOut)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename:
        raise HTTPException(400, "No filename")
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(400, f"Unsupported file type {ext}")
    # read content
    content = await file.read()
    validate_file_size(len(content), settings.max_upload_size_mb)
    # safe path
    safe_path = get_safe_path(settings.upload_dir, file.filename)
    safe_path.write_bytes(content)

    doc = Document(
        filename=safe_path.name,
        original_filename=file.filename,
        file_type=ext,
        file_size=len(content),
        file_path=str(safe_path),
        status="uploading"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # process synchronously for demo (in production use background tasks)
    try:
        ingest_document(db, doc, safe_path)
    except Exception as e:
        raise HTTPException(500, f"Ingestion failed: {e}")

    db.refresh(doc)
    return doc

@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.query(Document).order_by(Document.created_at.desc()).all()

@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id==document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc

@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id==document_id).first()
    if not doc:
        raise HTTPException(404, "Not found")
    # remove file
    try:
        Path(doc.file_path).unlink(missing_ok=True)
    except: pass
    db.delete(doc)
    db.commit()
    return {"message": "deleted"}

@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
def list_chunks(document_id: str, db: Session = Depends(get_db)):
    return db.query(DocumentChunk).filter(DocumentChunk.document_id==document_id).order_by(DocumentChunk.chunk_index).all()

@router.get("/{document_id}/equations")
def list_equations(document_id: str, db: Session = Depends(get_db)):
    from ..services.equations import list_equations as le
    return le(db, document_id)

@router.get("/{document_id}/pages")
def get_pages(document_id: str, db: Session = Depends(get_db)):
    from ..models.document import DocumentPage
    pages = db.query(DocumentPage).filter(DocumentPage.document_id==document_id).order_by(DocumentPage.page_number).all()
    return [{"id": p.id, "page_number": p.page_number, "text": p.text[:2000] if p.text else "", "char_count": p.char_count} for p in pages]

@router.post("/{document_id}/analyze-dataset")
def analyze_dataset_endpoint(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id==document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.file_type != ".csv":
        raise HTTPException(400, "Not a CSV dataset")
    path = Path(doc.file_path)
    result = analyze_dataset(path)
    return result

@router.get("/search")
def search(q: str, document_id: str = None, content_type: str = None, db: Session = Depends(get_db)):
    from ..services.retrieval import retrieve
    filters={}
    if content_type:
        filters["content_type"]=content_type
    doc_ids = [document_id] if document_id else None
    results = retrieve(db, q, top_k=10, document_ids=doc_ids, filters=filters if filters else None)
    return results

@router.post("/{document_id}/reprocess")
def reprocess(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id==document_id).first()
    if not doc:
        raise HTTPException(404, "Not found")
    path = Path(doc.file_path)
    if not path.exists():
        raise HTTPException(404, "File missing on disk")
    ingest_document(db, doc, path)
    return {"message": "reprocessed", "status": doc.status}
