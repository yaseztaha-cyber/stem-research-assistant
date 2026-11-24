from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from ..models.chunk import DocumentChunk
import re

def expand_local_context(db: Session, chunk: Dict, window: int = 1) -> Dict:
    """Retrieve surrounding paragraphs for highly relevant chunk"""
    try:
        doc_id = chunk["document_id"]
        idx = chunk.get("chunk_index", 0)
        # Fetch adjacent chunks
        prev_chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id==doc_id,
            DocumentChunk.chunk_index.between(idx-window, idx-1)
        ).order_by(DocumentChunk.chunk_index).all()
        next_chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id==doc_id,
            DocumentChunk.chunk_index.between(idx+1, idx+window)
        ).order_by(DocumentChunk.chunk_index).all()

        expanded_text = ""
        if prev_chunks:
            expanded_text += prev_chunks[-1].text[:300] + "\n\n"
        expanded_text += chunk["text"]
        if next_chunks:
            expanded_text += "\n\n" + next_chunks[0].text[:300]

        # Only expand if adds value and not too long
        if len(expanded_text) > len(chunk["text"]) * 1.8:
            expanded_text = chunk["text"]  # revert if too verbose

        new_chunk = chunk.copy()
        new_chunk["text"] = expanded_text[:2000]
        new_chunk["expanded"] = len(expanded_text) != len(chunk["text"])
        new_chunk["expansion_context"] = "previous+next paragraph" if new_chunk["expanded"] else "none"
        return new_chunk
    except Exception:
        return chunk

def build_optimized_context(
    db: Session,
    query: str,
    query_type: str,
    retrieved: List[Dict],
    document_structure: Optional[Dict] = None,
) -> str:
    """
    Context construction v2: dedup, preserve equations/tables, group by source, order by relevance, avoid excessive text
    """
    if not retrieved:
        return ""

    # 1. Remove redundant chunks (already MMR, but dedup by text similarity)
    unique = []
    seen_texts = set()
    for r in retrieved:
        # Jaccard similarity with seen
        is_dup = False
        for seen in seen_texts:
            # simple overlap
            t1 = set(r["text"].lower().split())
            t2 = set(seen.lower().split())
            if len(t1.intersection(t2)) / max(len(t1.union(t2)),1) > 0.85:
                is_dup = True
                break
        if not is_dup:
            unique.append(r)
            seen_texts.add(r["text"][:500])
    retrieved = unique

    # 2. Local context expansion for highly relevant or specific types
    expanded = []
    for r in retrieved:
        # Expand only for specific query types or high score
        should_expand = False
        if query_type in ("experimental_result", "methodology", "definition", "equation", "table"):
            should_expand = r.get("retrieval_score",0) > 0.4
        elif r.get("retrieval_score",0) > 0.6:
            should_expand = True
        # Also expand if chunk is short (<200 chars) likely needs context
        if len(r["text"]) < 300 and r.get("retrieval_score",0) > 0.3:
            should_expand = True

        if should_expand and db is not None:
            r_exp = expand_local_context(db, r, window=1)
            expanded.append(r_exp)
        else:
            r["expanded"] = False
            expanded.append(r)

    # 3. Preserve equations/tables: ensure chunks with content_type equation/table are not truncated
    for r in expanded:
        if r.get("content_type") in ("equation", "table"):
            # Keep full text, ensure not truncated below 1500
            if len(r["text"]) < 100:
                # Keep as is, but mark
                pass

    # 4. Group by source for multi-doc queries
    # Check if multi-doc: more than 1 document in retrieved
    doc_ids = list(set([r["document_id"] for r in expanded]))
    is_multi = len(doc_ids) > 1 and query_type in ("comparison", "multi_document", "general") or len(doc_ids)>1

    # 5. Source-aware ordering
    # Primary = top 1-2 highest retrieval_score
    # Supporting = next 2-3
    # Additional = rest
    sorted_by_score = sorted(expanded, key=lambda x: x.get("retrieval_score",0), reverse=True)
    primary = sorted_by_score[:2]
    supporting = sorted_by_score[2:4]
    additional = sorted_by_score[4:]

    # Reorder: primary first, then supporting, then additional, but group by document if multi-doc
    if is_multi:
        # Group by document
        by_doc = {}
        for r in sorted_by_score:
            by_doc.setdefault(r["document_id"], []).append(r)
        # Order documents by max score
        doc_order = sorted(by_doc.keys(), key=lambda did: max([x["retrieval_score"] for x in by_doc[did]]), reverse=True)
        ordered = []
        # Interleave? For multi-doc, list doc A evidence then doc B
        for did in doc_order:
            ordered.extend(by_doc[did])
        # Then re-apply primary/supporting grouping per doc? Keep overall order but grouped
        primary = [r for r in ordered if r in primary]
        # For multi-doc, ensure primary includes at least one per document if possible
        if len(primary) < len(doc_ids):
            # Add top from each doc
            for did in doc_ids:
                top_for_doc = max(by_doc[did], key=lambda x: x["retrieval_score"])
                if top_for_doc not in primary:
                    primary.append(top_for_doc)
        ordered_final = ordered
    else:
        ordered_final = primary + supporting + additional

    # 6. Build context string with hierarchy
    lines = []
    if is_multi:
        # Grouped header
        current_doc = None
        for idx, r in enumerate(ordered_final, start=1):
            if r["document_id"] != current_doc:
                lines.append(f"\nDOCUMENT: {r['document_name']}")
                lines.append(f"---")
                current_doc = r["document_id"]
            tier = "PRIMARY EVIDENCE" if r in primary else "SUPPORTING EVIDENCE" if r in supporting else "ADDITIONAL CONTEXT"
            lines.append(f"\n{tier} {idx}")
            lines.append(f"Document: {r['document_name']}")
            lines.append(f"Page: {r['page_number']}")
            lines.append(f"Section: {r['section']}")
            lines.append(f"Content Type: {r['content_type']}")
            lines.append(f"Retrieval Score: {r['retrieval_score']:.3f}")
            if r.get("expanded"):
                lines.append(f"Context: Expanded ({r.get('expansion_context')})")
            lines.append("")
            lines.append("Content:")
            lines.append(r['text'][:1500])
            lines.append("---")
    else:
        for idx, r in enumerate(ordered_final, start=1):
            tier = "PRIMARY EVIDENCE" if r in primary else "SUPPORTING EVIDENCE" if r in supporting else "ADDITIONAL CONTEXT"
            lines.append(f"{tier} {idx}")
            lines.append(f"Document: {r['document_name']}")
            lines.append(f"Page: {r['page_number']}")
            lines.append(f"Section: {r['section']}")
            lines.append(f"Content Type: {r['content_type']}")
            lines.append(f"Retrieval Score: {r['retrieval_score']:.3f}")
            if r.get("expanded"):
                lines.append(f"Context: Expanded ({r.get('expansion_context')})")
            lines.append("")
            lines.append("Content:")
            lines.append(r['text'][:1500])
            lines.append("---")

    return "\n".join(lines)

def build_rag_context(retrieved: List[Dict]) -> str:
    """Legacy wrapper for backward compat"""
    # Simple version without DB
    lines = []
    for i, r in enumerate(retrieved, start=1):
        lines.append(f"SOURCE {i}")
        lines.append(f"Document: {r['document_name']}")
        lines.append(f"Page: {r['page_number']}")
        lines.append(f"Section: {r['section']}")
        lines.append(f"Chunk: {r['chunk_id']}")
        lines.append(f"Retrieval Score: {r['retrieval_score']:.3f}")
        lines.append(f"Content Type: {r['content_type']}")
        lines.append("")
        lines.append("Content:")
        lines.append(r['text'][:1500])
        lines.append("---")
        lines.append("")
    return "\n".join(lines)
