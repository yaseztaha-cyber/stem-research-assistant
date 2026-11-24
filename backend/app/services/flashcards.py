from sqlalchemy.orm import Session
from typing import List, Dict
import re
import random
from ..models.learning import Flashcard
from ..models.chunk import DocumentChunk

TYPES = ["definition","concept","equation","variable","unit","process","cause/effect","comparison","experimental result","application"]

def generate_flashcards(db: Session, document_id: str = None, collection_id: str = None, limit: int = 10) -> List[Dict]:
    # retrieve relevant chunks as source material; avoid trivial copying
    q = db.query(DocumentChunk)
    if document_id:
        q = q.filter(DocumentChunk.document_id==document_id)
    if collection_id:
        from ..models.collection import CollectionDocument
        doc_ids = [r.document_id for r in db.query(CollectionDocument).filter(CollectionDocument.collection_id==collection_id).all()]
        if doc_ids:
            q = q.filter(DocumentChunk.document_id.in_(doc_ids))
    chunks = q.limit(50).all()
    if not chunks:
        return []

    cards=[]
    for ch in chunks:
        if len(cards)>=limit:
            break
        text = ch.text
        # generate different types based on content
        if ch.content_type=="definition" or "is defined as" in text.lower():
            # definition card
            sentences = re.split(r"(?<=[.!?])\s+", text)
            if len(sentences)>=1:
                # extract term
                term_match = re.search(r"([A-Z][a-zA-Z\s]{2,30})\s+is defined as", text)
                term = term_match.group(1).strip() if term_match else ch.section or "Concept"
                answer = sentences[0][:300]
                question = f"What is {term}?"
                cards.append({"question": question, "answer": answer, "type":"definition", "difficulty":"easy", "source": {"document_id": ch.document_id, "page": ch.page_number, "chunk_id": ch.id}})
        elif ch.content_type=="equation" or "=" in text and len(text)<300:
            eq_match = re.search(r"([A-Za-z0-9ΔημΩ]+\s*=\s*[^\n]{2,60})", text)
            if eq_match:
                eq = eq_match.group(1).strip()
                variables = re.findall(r"\b([A-Z])\b", eq)
                if variables:
                    var = random.choice(variables)
                    cards.append({"question": f"In the equation {eq}, what does '{var}' represent?", "answer": f"Variable {var} in context: {text[:200]}", "type":"variable", "difficulty":"medium", "source":{"document_id": ch.document_id, "page": ch.page_number, "chunk_id": ch.id}})
                else:
                    cards.append({"question": f"State the equation: {eq[:30]}...", "answer": eq, "type":"equation", "difficulty":"medium", "source":{"document_id": ch.document_id, "page": ch.page_number, "chunk_id": ch.id}})
        elif ch.content_type=="result" or "results" in (ch.section or "").lower():
            sentences = re.split(r"(?<=[.!?])\s+", text)
            if sentences and any("%" in s or "increase" in s.lower() for s in sentences):
                s = next((x for x in sentences if "%" in x), sentences[0])
                cards.append({"question": f"What experimental result is reported? (Page {ch.page_number})", "answer": s[:300], "type":"experimental result", "difficulty":"medium", "source":{"document_id": ch.document_id, "page": ch.page_number, "chunk_id": ch.id}})
        else:
            # generic concept card but ensure not trivial copy: transform
            sentences = re.split(r"(?<=[.!?])\s+", text)
            if len(sentences)>=2 and len(text)>100:
                question = f"Explain: {sentences[0][:80]}... (What mechanism is described?)"
                answer = " ".join(sentences[1:])[:300]
                cards.append({"question": question, "answer": answer, "type":"concept", "difficulty":"medium", "source":{"document_id": ch.document_id, "page": ch.page_number, "chunk_id": ch.id}})

    # dedupe and ensure quality: filter trivial cards where question==answer fragment copy
    filtered=[]
    seen=set()
    for c in cards:
        key=(c["question"][:30], c["answer"][:30])
        if key in seen: continue
        seen.add(key)
        # ensure not too short
        if len(c["answer"])<20: continue
        filtered.append(c)
    # save to DB
    for card in filtered[:limit]:
        obj = Flashcard(document_id=card["source"]["document_id"] if card["source"] else None, question=card["question"], answer=card["answer"], type=card["type"], difficulty=card["difficulty"], source=card["source"])
        db.add(obj)
    db.commit()
    return filtered[:limit]
