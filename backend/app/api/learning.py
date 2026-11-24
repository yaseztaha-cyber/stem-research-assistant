from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.flashcards import generate_flashcards
from ..services.problems import generate_problems
from ..services.questions import generate_research_questions
from ..services.equations import list_equations, explain_equation
from ..services.citations import generate_citation
from ..models.learning import Flashcard, PracticeProblem, ResearchQuestion

router = APIRouter(prefix="/learning", tags=["learning"])

@router.post("/flashcards")
def create_flashcards(document_id: str = None, collection_id: str = None, limit: int = 10, db: Session = Depends(get_db)):
    cards = generate_flashcards(db, document_id, collection_id, limit)
    return cards

@router.get("/flashcards")
def list_flashcards(document_id: str = None, db: Session = Depends(get_db)):
    q = db.query(Flashcard)
    if document_id:
        q = q.filter(Flashcard.document_id==document_id)
    return [{"id": f.id, "question": f.question, "answer": f.answer, "type": f.type, "difficulty": f.difficulty, "source": f.source} for f in q.all()]

@router.post("/problems")
def create_problems(document_id: str = None, collection_id: str = None, difficulty: str = "medium", limit: int = 5, db: Session = Depends(get_db)):
    problems = generate_problems(db, document_id, collection_id, difficulty, limit)
    return problems

@router.get("/problems")
def list_problems(document_id: str = None, db: Session = Depends(get_db)):
    q = db.query(PracticeProblem)
    if document_id:
        q = q.filter(PracticeProblem.document_id==document_id)
    return [{"id": p.id, "problem": p.problem, "known_values": p.known_values, "unknown": p.unknown, "relevant_equation": p.relevant_equation, "solution": p.solution, "unit_verification": p.unit_verification, "final_answer": p.final_answer, "difficulty": p.difficulty, "source": p.source} for p in q.all()]

@router.post("/questions")
def create_questions(document_id: str = None, collection_id: str = None, limit: int = 8, db: Session = Depends(get_db)):
    qs = generate_research_questions(db, document_id, collection_id, limit)
    return qs

@router.get("/questions")
def list_questions(document_id: str = None, db: Session = Depends(get_db)):
    q = db.query(ResearchQuestion)
    if document_id:
        q = q.filter(ResearchQuestion.document_id==document_id)
    return [{"id": r.id, "question": r.question, "category": r.category, "source_grounded": r.source_grounded, "evidence": r.evidence} for r in q.all()]

@router.get("/equations")
def equations(document_id: str = None, search: str = None, db: Session = Depends(get_db)):
    return list_equations(db, document_id, search)

@router.get("/equations/{equation_id}/explain")
def explain_eq(equation_id: str, db: Session = Depends(get_db)):
    res = explain_equation(db, equation_id)
    if not res:
        return {"error": "Not found"}
    return res

@router.get("/citations/{document_id}")
def citation(document_id: str, style: str = "apa", db: Session = Depends(get_db)):
    return generate_citation(db, document_id, style)
