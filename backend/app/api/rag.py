from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..schemas.rag import RagQueryIn, RagQueryOut, ExplainIn
from ..services.rag import rag_query, compare_documents
from ..services.explanation import explain_concept
from ..services.retrieval import retrieve, build_rag_context

router = APIRouter(prefix="/rag", tags=["rag"])

@router.post("/query", response_model=RagQueryOut)
async def query_rag(body: RagQueryIn, db: Session = Depends(get_db)):
    # optional conversation history
    history = None
    if body.conversation_id:
        from ..models.conversation import Message, Conversation
        msgs = db.query(Message).filter(Message.conversation_id==body.conversation_id).order_by(Message.created_at).all()
        history = [{"role": m.role, "content": m.content} for m in msgs]
        # also create conversation if not exists? handled elsewhere
    result = await rag_query(db, body.query, top_k=body.top_k or 8, document_ids=body.document_ids, collection_id=body.collection_id, filters=body.filters, grounded_mode=body.grounded_mode, conversation_history=history)
    # if conversation_id, persist messages
    if body.conversation_id:
        from ..models.conversation import Message
        user_msg = Message(conversation_id=body.conversation_id, role="user", content=body.query)
        db.add(user_msg)
        assistant_msg = Message(conversation_id=body.conversation_id, role="assistant", content=result["answer"], grounding_score=result["grounding"]["score"], claims=result["claims"], evidence=result["retrieved"], citations=result["citations"], retrieval_metadata={"latency": result["latency"], "model": result["model"]})
        db.add(assistant_msg)
        db.commit()
    # observability
    from ..services.observability import log_request
    log_request(result["request_id"], "anon", ",".join(body.document_ids or []), "/rag/query", result["latency"], result["model"], len(result["retrieved"]))
    return result

@router.post("/explain")
async def explain(body: ExplainIn, db: Session = Depends(get_db)):
    result = await explain_concept(db, body.concept, body.level, body.document_ids, body.collection_id)
    return result

@router.post("/compare")
async def compare(query: str, document_ids: str, db: Session = Depends(get_db)):
    ids = document_ids.split(",")
    result = await compare_documents(db, query, ids)
    return result

@router.post("/evidence")
def evidence(query: str, document_id: str = None, db: Session = Depends(get_db)):
    doc_ids = [document_id] if document_id else None
    retrieved = retrieve(db, query, top_k=5, document_ids=doc_ids)
    return {"query": query, "evidence": retrieved, "context": build_rag_context(retrieved)}

@router.get("/query-classify")
def query_classify(q: str):
    from ..services.query_classifier import classify_query
    return classify_query(q)

@router.get("/trace")
def trace(query: str, document_id: str = None, db: Session = Depends(get_db)):
    from ..services.retrieval import retrieve_with_trace
    doc_ids = [document_id] if document_id else None
    retrieved, trace = retrieve_with_trace(db, query, top_k=5, document_ids=doc_ids)
    return {"query": query, "trace": trace, "retrieved": retrieved}

@router.get("/validate-equation")
def validate_equation(equation: str, values: str = None):
    from ..services.math_validation import full_math_validation
    import json
    vals = json.loads(values) if values else None
    return full_math_validation(equation, vals)

@router.get("/validate-citation")
def validate_citation(answer: str, db: Session = Depends(get_db)):
    from ..services.grounding import verify_citations_v2
    from ..services.retrieval import retrieve
    # dummy retrieve for context
    retrieved = retrieve(db, answer[:100], top_k=5)
    return verify_citations_v2(answer, retrieved)

