from sqlalchemy.orm import Session
from typing import List, Dict
import re
from ..models.chunk import DocumentChunk
from ..models.learning import ResearchQuestion

CATEGORIES = ["comprehension","application","experimental","comparative","causal","design","research-gap","advanced"]

def generate_research_questions(db: Session, document_id: str = None, collection_id: str = None, limit: int = 8) -> List[Dict]:
    q = db.query(DocumentChunk)
    if document_id:
        q = q.filter(DocumentChunk.document_id==document_id)
    if collection_id:
        from ..models.collection import CollectionDocument
        doc_ids = [r.document_id for r in db.query(CollectionDocument).filter(CollectionDocument.collection_id==collection_id).all()]
        if doc_ids:
            q = q.filter(DocumentChunk.document_id.in_(doc_ids))
    chunks = q.limit(40).all()
    if not chunks:
        return []

    # templates per category based on source evidence
    templates = {
        "comprehension": "What does the source define as '{term}' on page {page}?",
        "application": "How could the {concept} described on page {page} be applied to a different system with ΔT = 50K?",
        "experimental": "What experimental variable could explain the discrepancy between reported and expected {metric} in the results section?",
        "comparative": "How does the efficiency reported in this document compare to the method on page {page}?",
        "causal": "Why does increasing {variable} lead to {effect} according to the source mechanism?",
        "design": "Design an experiment to isolate the effect of {variable} on {outcome} using the setup described.",
        "research-gap": "What limitation or future work is implied but not explicitly tested in section '{section}'?",
        "advanced": "What are the thermodynamic limits of the proposed system and what factors (material, geometry, ΔT) bound it?",
    }

    questions=[]
    for ch in chunks:
        if len(questions)>=limit:
            break
        txt = ch.text
        section = ch.section or "Results"
        page = ch.page_number
        # extract terms
        term_match = re.search(r"([A-Z][a-z]{3,12})\s+(?:effect|system|generator|material|output)", txt)
        term = term_match.group(1) if term_match else "thermoelectric effect"
        concept = term
        variable = "temperature gradient" if "temperature" in txt.lower() else "current"
        effect = "electrical output"
        metric = "power output"
        outcome = "voltage"
        # decide category via content_type or heuristic
        if ch.content_type=="definition":
            cat="comprehension"
            questions.append({"question": templates[cat].format(term=concept, page=page), "category":cat, "source_grounded": True, "evidence":{"document_id":ch.document_id,"page":page,"chunk_id":ch.id}})
        elif ch.content_type=="result":
            cat="experimental"
            questions.append({"question": templates[cat].format(metric=metric), "category":cat, "source_grounded": True, "evidence":{"document_id":ch.document_id,"page":page,"chunk_id":ch.id}})
        elif ch.content_type=="procedure":
            cat="design"
            questions.append({"question": templates[cat].format(variable=variable, outcome=outcome), "category":cat, "source_grounded": True, "evidence":{"document_id":ch.document_id,"page":page,"chunk_id":ch.id}})
        else:
            # rotate.categories
            cat = CATEGORIES[len(questions)%len(CATEGORIES)]
            # generate appropriate
            if cat=="causal":
                questions.append({"question": templates[cat].format(variable=variable, effect=effect), "category":cat, "source_grounded": True, "evidence":{"document_id":ch.document_id,"page":page,"chunk_id":ch.id}})
            elif cat=="research-gap":
                questions.append({"question": templates[cat].format(section=section), "category":cat, "source_grounded": False, "evidence":{"document_id":ch.document_id,"page":page,"chunk_id":ch.id}})
            else:
                try:
                    questions.append({"question": templates[cat].format(concept=concept, page=page, section=section, term=term, variable=variable, effect=effect, metric=metric, outcome=outcome), "category":cat, "source_grounded": cat not in ["advanced","research-gap"], "evidence":{"document_id":ch.document_id,"page":page,"chunk_id":ch.id}})
                except:
                    questions.append({"question": f"How would changing ΔT affect the measured output on page {page}?", "category":"causal","source_grounded":True,"evidence":{"document_id":ch.document_id,"page":page,"chunk_id":ch.id}})

    # ensure diversity: at least one of each major? truncate to limit and add advanced
    if len(questions)<limit:
        questions.append({"question": "What factors limit the efficiency of the proposed system according to thermodynamic principles? [GENERATED extension]", "category":"advanced","source_grounded": False, "evidence": {"document_id":chunks[0].document_id if chunks else None,"page":1}})

    # save
    for qq in questions[:limit]:
        obj = ResearchQuestion(document_id=qq["evidence"].get("document_id"), question=qq["question"], category=qq["category"], source_grounded=qq["source_grounded"], evidence=qq["evidence"])
        db.add(obj)
    db.commit()
    return questions[:limit]
