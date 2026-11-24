from sqlalchemy.orm import Session
from ..models.chunk import DocumentChunk
from ..models.document import Document
import re

def analyze_lab_manual(db: Session, document_id: str):
    doc = db.query(Document).filter(Document.id==document_id).first()
    if not doc:
        return {"error": "Not found"}
    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id==document_id).all()
    full = " ".join([c.text for c in chunks])

    def extract_section(keywords):
        for ch in chunks:
            if any(k.lower() in (ch.section or "").lower() for k in keywords):
                return ch.text[:800]
        # fallback search in text
        low = full.lower()
        for kw in keywords:
            idx = low.find(kw.lower())
            if idx!=-1:
                return full[max(0,idx-100): idx+700]
        return None

    objective = extract_section(["objective","aim","purpose"]) or "Objective not explicitly stated in source."
    materials = extract_section(["materials","equipment","apparatus"]) or "Materials not listed explicitly."
    safety = extract_section(["safety","hazard","precaution","warning"])
    procedure = extract_section(["procedure","method","steps","protocol"]) or "Procedure not detailed in source."
    variables = extract_section(["variables","parameters"])
    measurements = extract_section(["measurements","observations","data"])
    expected = extract_section(["expected","observations","results"])
    calculations = extract_section(["calculations","equations","formula"])
    questions = extract_section(["questions","exercises"])
    errors = extract_section(["error","sources of error","uncertainty"])

    # ensure safety prominent: if found, keep top
    safety_text = safety if safety else "No explicit safety information found in document — consult instructor. [GENERATED caution]"

    # extract procedures as list
    procedure_steps = []
    if procedure and procedure!="Procedure not detailed in source.":
        steps = re.split(r"\n+|\d+\.\s+", procedure)
        procedure_steps = [s.strip() for s in steps if len(s.strip())>15][:8]

    return {
        "document_id": document_id,
        "document_name": doc.original_filename,
        "objective": objective,
        "materials": materials,
        "safety_information": safety_text,
        "safety_prominent": True,
        "procedure": procedure,
        "procedure_steps": procedure_steps,
        "variables": variables,
        "measurements": measurements,
        "expected_observations": expected,
        "calculations": calculations,
        "questions": questions,
        "sources_of_error": errors,
        "note": "Do not invent experimental procedures absent from source; missing fields indicate absence in source material."
    }
