import shutil
from pathlib import Path
from sqlalchemy.orm import Session
from ..models.document import Document, DocumentPage, DocumentSection
from ..models.chunk import DocumentChunk
from ..models.embedding import Embedding
from ..services.parsing import parse_document
from ..services.chunking import structure_aware_chunk
from ..core.embedding_provider import get_global_embedding_provider
from ..config import settings
import uuid

def ingest_document(db: Session, document: Document, file_path: Path):
    """Full ingestion pipeline: parse -> structure detection -> chunking -> embeddings -> equations"""
    try:
        document.status = "processing"
        db.commit()

        import time
        t_parse_start = time.time()
        parsed = parse_document(file_path, document.file_type)
        pages = parsed.get("pages", [])
        sections = parsed.get("sections", [])
        equations_data = parsed.get("equations", [])
        tables = parsed.get("tables", [])
        figures = parsed.get("figures", [])
        doc_metadata = parsed.get("metadata", {})
        # enrich metadata with v0.2 fields
        doc_metadata["tables"] = tables[:10]
        doc_metadata["figures"] = figures[:10]
        doc_metadata["parser"] = parsed.get("parser", "pypdf")
        doc_metadata["extraction_time_ms"] = int((time.time() - t_parse_start)*1000)

        # update document metadata & page count
        document.page_count = len(pages)
        document.doc_metadata = doc_metadata
        # source quality heuristic
        # If contains "lab manual" or "experimental" etc
        full_low = parsed.get("full_text","")[:3000].lower()
        if "abstract" in full_low and "references" in full_low:
            document.source_quality = "peer-reviewed paper"
        elif "lab" in document.original_filename.lower() or "procedure" in full_low:
            document.source_quality = "lab manual"
        elif document.file_type==".csv":
            document.source_quality = "dataset"
        elif "textbook" in document.original_filename.lower():
            document.source_quality = "textbook"

        db.commit()

        # clear previous pages/sections/chunks if re-ingest
        db.query(DocumentPage).filter(DocumentPage.document_id==document.id).delete()
        db.query(DocumentSection).filter(DocumentSection.document_id==document.id).delete()
        db.query(DocumentChunk).filter(DocumentChunk.document_id==document.id).delete()
        db.flush()

        # save pages
        page_objs = []
        for p in pages:
            obj = DocumentPage(document_id=document.id, page_number=p["page_number"], text=p["text"][:10000], char_count=p["char_count"])
            db.add(obj)
            page_objs.append(obj)
        db.flush()

        # map page_number to page_id for sections
        page_map = {o.page_number: o.id for o in page_objs}

        for sec in sections:
            obj = DocumentSection(
                document_id=document.id,
                page_id=page_map.get(sec.get("page_number")),
                page_number=sec.get("page_number"),
                title=sec.get("title")[:500] if sec.get("title") else None,
                level=sec.get("level",1),
                heading_hierarchy=sec.get("heading_hierarchy"),
                section_type=sec.get("section_type"),
                text=sec.get("text")[:8000],
                order_index=sec.get("order_index",0)
            )
            db.add(obj)
        db.flush()

        # chunking
        chunks_data = structure_aware_chunk(pages, sections)

        # embeddings: batch
        texts = [c["text"] for c in chunks_data]
        provider = get_global_embedding_provider()
        vectors = provider.embed_texts(texts) if texts else []

        # save chunks + embeddings
        from ..models.equation import Equation
        # clear old equations
        db.query(Equation).filter(Equation.document_id==document.id).delete()

        for idx, c in enumerate(chunks_data):
            chunk = DocumentChunk(
                document_id=document.id,
                document_name=document.original_filename,
                page_number=c["page_number"],
                section=c["section"],
                heading_hierarchy=c["heading_hierarchy"],
                chunk_index=c["chunk_index"],
                text=c["text"],
                content_type=c["content_type"],
                token_count=c["token_count"],
                char_count=c["char_count"],
                chunk_metadata={"section_type": c.get("section_type")}
            )
            db.add(chunk)
            db.flush()
            # embedding
            vec = vectors[idx] if idx < len(vectors) else None
            if vec is not None:
                emb = Embedding(chunk_id=chunk.id, document_id=document.id, provider=settings.embedding_provider, vector=vec, dim=str(len(vec)) if isinstance(vec,list) else None)
                db.add(emb)

        # save equations with v0.2 enriched fields (raw, normalized, latex, confidence)
        for eq in equations_data:
            eq_text = eq.get("equation_text") or eq.get("raw_expression") or ""
            if not eq_text:
                continue
            linked_chunk_id = None
            # try to link to chunk that contains equation text
            # search actual DB chunks we just created (by text)
            try:
                # find chunk containing eq substring
                for ch in db.query(DocumentChunk).filter(DocumentChunk.document_id==document.id).all():
                    if eq_text[:15] in ch.text:
                        linked_chunk_id = ch.id
                        break
            except Exception:
                pass
            # math validation
            math_valid = None
            try:
                from .math_validation import full_math_validation
                math_valid = full_math_validation(eq_text)
            except Exception:
                pass
            eobj = Equation(
                document_id=document.id,
                page_number=eq.get("page"),
                section=eq.get("section"),
                equation_text=eq_text,
                variables=eq.get("variables"),
                units=eq.get("units"),
                context=eq.get("context")[:1000] if eq.get("context") else None,
                confidence=eq.get("confidence", 0.7 if eq.get("uncertain") or eq.get("uncertainty") else 0.95),
                uncertain=eq.get("uncertain", eq.get("uncertainty", False)),
                chunk_id=linked_chunk_id
            )
            # store extra validation in chunk_metadata-like via variables extra?
            # We keep confidence and uncertain; validation can be queried via API
            db.add(eobj)

        document.status = "ready"
        db.commit()
        # Invalidate caches for retrieval/evaluation
        try:
            from .cache import retrieval_cache, evaluation_cache, document_cache
            retrieval_cache.invalidate("retrieval")
            evaluation_cache.invalidate("evaluation")
        except Exception:
            pass
        # Observability
        try:
            from .observability import logger
            logger.info(f"Ingestion doc={document.id} pages={len(pages)} chunks={len(chunks_data)} equations={len(equations_data)} tables={len(tables)} figures={len(figures)}")
        except Exception:
            pass
        return {"chunks": len(chunks_data), "pages": len(pages), "equations": len(equations_data), "tables": len(tables), "figures": len(figures)}

    except Exception as e:
        document.status = "failed"
        document.error_message = str(e)[:2000]
        db.commit()
        raise e
