from typing import Dict
from sqlalchemy.orm import Session
from ..models.document import Document

def generate_citation(db: Session, document_id: str, style: str = "apa") -> Dict:
    doc = db.query(Document).filter(Document.id==document_id).first()
    if not doc:
        return {"error": "Document not found"}
    meta = doc.doc_metadata or {}
    title = meta.get("title") or doc.original_filename.replace(".pdf","")
    authors = meta.get("author") or meta.get("authors")
    year = meta.get("year") or meta.get("publication_year")
    journal = meta.get("journal") or meta.get("conference")
    doi = meta.get("doi")
    volume = meta.get("volume")
    pages = meta.get("pages")

    # Handle authors as string or list
    if isinstance(authors, list):
        author_str = ", ".join(authors)
    elif isinstance(authors, str):
        author_str = authors
    else:
        author_str = None

    def apa():
        parts=[]
        if author_str:
            parts.append(author_str)
        else:
            parts.append("Metadata unavailable (authors)")
        if year:
            parts.append(f"({year}).")
        else:
            parts.append("(n.d.).")
        parts.append(f"{title}.")
        if journal:
            parts.append(f"{journal},")
        if volume:
            parts.append(f"{volume},")
        if pages:
            parts.append(f"{pages}.")
        if doi:
            parts.append(f"https://doi.org/{doi}")
        else:
            if not journal:
                parts.append("[No DOI/journal metadata available]")
        return " ".join(parts)

    def ieee():
        auth = author_str or "Metadata unavailable"
        yr = year or "n.d."
        title_part = f'"{title},"'
        journal_part = f"{journal}," if journal else ""
        doi_part = f"doi: {doi}." if doi else "[No DOI]"
        return f"{auth}, {title_part} {journal_part} {yr}. {doi_part}"

    def mla():
        auth = author_str or "Metadata unavailable"
        yr = year or "n.d."
        return f'{auth}. "{title}." {journal or "Unknown Journal"}, {yr}. DOI: {doi or "unavailable"}.'

    style_low = style.lower()
    if style_low=="ieee":
        formatted = ieee()
    elif style_low=="mla":
        formatted = mla()
    else:
        formatted = apa()

    # Never fabricate missing metadata: if missing, we inserted placeholders above
    has_complete = bool(author_str and year and (journal or doi))
    note = None
    if not has_complete:
        note = "Metadata incomplete — citation uses available information only; missing fields marked as unavailable rather than guessed."

    return {
        "document_id": document_id,
        "style": style,
        "formatted": formatted,
        "metadata": {"title": title, "authors": author_str, "year": year, "journal": journal, "doi": doi, "volume": volume, "pages": pages},
        "complete": has_complete,
        "note": note
    }
