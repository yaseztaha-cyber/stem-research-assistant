from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.paper_analysis import analyze_paper
from ..services.lab_manual import analyze_lab_manual

router = APIRouter(prefix="/analysis", tags=["analysis"])

@router.get("/paper/{document_id}")
def paper_analysis(document_id: str, db: Session = Depends(get_db)):
    return analyze_paper(db, document_id)

@router.get("/lab/{document_id}")
def lab_analysis(document_id: str, db: Session = Depends(get_db)):
    return analyze_lab_manual(db, document_id)
