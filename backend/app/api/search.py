from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_
from ..database import get_db
from ..models.chunk import DocumentChunk
from ..models.learning import Flashcard, PracticeProblem, ResearchQuestion
from ..models.equation import Equation
from ..models.document import Document
from ..services.retrieval import retrieve

router = APIRouter(prefix="/search", tags=["search"])

@router.get("")
def global_search(q: str, db: Session = Depends(get_db)):
    if not q or len(q.strip())<2:
        return {"error": "query too short"}
    # semantic via retrieval + keyword search across models
    chunks = retrieve(db, q, top_k=6)
    # exact search in other tables
    equations = db.query(Equation).filter(Equation.equation_text.ilike(f"%{q}%")).limit(5).all()
    flashcards = db.query(Flashcard).filter(or_(Flashcard.question.ilike(f"%{q}%"), Flashcard.answer.ilike(f"%{q}%"))).limit(5).all()
    problems = db.query(PracticeProblem).filter(PracticeProblem.problem.ilike(f"%{q}%")).limit(5).all()
    questions = db.query(ResearchQuestion).filter(ResearchQuestion.question.ilike(f"%{q}%")).limit(5).all()
    docs = db.query(Document).filter(Document.original_filename.ilike(f"%{q}%")).limit(5).all()
    return {
        "chunks": chunks,
        "equations": [{"id": e.id, "equation_text": e.equation_text, "page": e.page_number} for e in equations],
        "flashcards": [{"id": f.id, "question": f.question} for f in flashcards],
        "problems": [{"id": p.id, "problem": p.problem} for p in problems],
        "research_questions": [{"id": r.id, "question": r.question} for r in questions],
        "documents": [{"id": d.id, "filename": d.original_filename} for d in docs],
    }
