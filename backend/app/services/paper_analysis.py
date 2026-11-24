from typing import Dict, List
from sqlalchemy.orm import Session
from ..models.chunk import DocumentChunk
from ..models.document import Document
import re

PAPER_SECTIONS = ["abstract","introduction","background","methods","experimental setup","results","discussion","conclusion","references"]

def analyze_paper(db: Session, document_id: str) -> Dict:
    doc = db.query(Document).filter(Document.id==document_id).first()
    if not doc:
        return {"error": "Document not found"}
    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id==document_id).all()
    sections = {}
    for ch in chunks:
        sec_type = (ch.section or "").lower()
        for ps in PAPER_SECTIONS:
            if ps in sec_type:
                sections.setdefault(ps, []).append(ch.text)

    # heuristic extraction
    def get_section_text(name):
        return " ".join(sections.get(name, []))[:2000]

    abstract = get_section_text("abstract")
    intro = get_section_text("introduction")
    methods = get_section_text("methods") or get_section_text("experimental setup")
    results = get_section_text("results")
    discussion = get_section_text("discussion")
    conclusion = get_section_text("conclusion")

    # research objective: first sentences of abstract/intro
    objective = (abstract.split(".")[0] if abstract else intro.split(".")[0] if intro else "Objective not explicitly stated in retrieved sections.")[:400]

    # methodology: look for procedure-like chunks
    methodology = methods[:800] if methods else "Methodology not clearly detected."

    # variables: extract from text patterns like "temperature, voltage"
    variables = []
    for ch in chunks:
        if "variable" in ch.text.lower() or "parameter" in ch.text.lower():
            # extract nouns?
            candidates = re.findall(r"\b(temperature|voltage|current|power|efficiency|resistance|ΔT|heat|output)\b", ch.text, re.IGNORECASE)
            variables.extend(candidates)
    variables = list(set(variables))[:8]

    # experimental setup
    setup = methods[:600] if methods else "Experimental setup not detailed in sources."

    # main findings
    findings = results[:800] if results else "Main findings not explicitly extracted; see results section."

    # limitations: search for "limitation", "future work", "however", "although"
    limitations_candidates = []
    for ch in chunks:
        low = ch.text.lower()
        if any(k in low for k in ["limitation", "future work", "however", "although", "limited", "constraint"]):
            limitations_candidates.append(ch.text[:300])
    limitations_source = limitations_candidates[:2] if limitations_candidates else []
    limitations_generated = ["AI-inferred limitations should be verified: e.g., sample size, temperature range bounded, material degradation not discussed. [GENERATED]"] if not limitations_candidates else []

    # evidence: top chunks
    evidence = [{"document": doc.original_filename, "page": ch.page_number, "section": ch.section, "text": ch.text[:400], "chunk_id": ch.id} for ch in chunks[:3]]

    # research gaps
    gaps = []
    if not discussion:
        gaps.append("Discussion section missing or minimal — research gaps not explicitly stated. [SOURCE observation]")
    gaps.append("Potential gap: Long-term stability and scalability not evaluated in the provided material. [GENERATED if not in source]")

    return {
        "document_id": document_id,
        "document_name": doc.original_filename,
        "sections_detected": list(sections.keys()),
        "research_objective": objective,
        "methodology": methodology,
        "variables": variables,
        "experimental_setup": setup,
        "main_findings": findings,
        "limitations": {"source_derived": limitations_source, "ai_inferred": limitations_generated},
        "evidence": evidence,
        "potential_research_gaps": gaps,
        "metadata": doc.doc_metadata,
    }
