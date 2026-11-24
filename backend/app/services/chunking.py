from typing import List, Dict
import re

# Content type detection - prioritized for scientific accuracy
def detect_content_type(text: str, heading: str = "") -> str:
    low = text.lower()
    heading_low = heading.lower()
    # Table has highest priority when text contains table markers (for table questions)
    if ("|" in text and text.count("|")>=2) or ("table:" in low and ("delta" in low or "|" in text)):
        return "table"
    if any(k in low for k in ["definition:", "is defined as", "refers to"]):
        return "definition"
    if any(k in low for k in ["equation", "formula"]) or re.search(r"[A-Za-z]\s*=\s*[A-Za-z0-9]", text):
        if len(text)<400 and "=" in text:
            return "equation"
    if any(k in heading_low for k in ["procedure", "method", "experimental setup"]):
        # But if text is clearly result table, don't override
        if "table:" in low or "|" in text:
            return "table"
        return "procedure"
    if any(k in heading_low for k in ["result"]):
        if "|" in text:
            return "table"
        return "result"
    if "reference" in heading_low:
        return "reference"
    if "discussion" in heading_low:
        return "discussion"
    return "paragraph"

def structure_aware_chunk(pages: List[Dict], sections: List[Dict], max_tokens: int = 400, overlap: int = 50) -> List[Dict]:
    """
    Implements structure-aware chunking respecting:
    - heading boundaries
    - paragraph boundaries
    - equation boundaries (keep equations intact)
    - page boundaries (preserve page number)
    - semantic similarity (approx via paragraph grouping; true semantic chunking would require embeddings)
    - Creates overlapping chunks for continuity but respects structure (overlap only within same section)
    """
    chunks = []
    chunk_idx = 0

    # If sections provided, chunk each section separately
    for sec in sections:
        sec_text = sec.get("text","").strip()
        if not sec_text:
            continue
        heading = sec.get("title","")
        heading_hierarchy = sec.get("heading_hierarchy", heading)
        section_type = sec.get("section_type","general")
        page_num = sec.get("page_number", 1)

        # Split by paragraphs (double newline or single newline with heuristic)
        paragraphs = re.split(r"\n\s*\n", sec_text)
        # Further split long paragraphs into sentences
        expanded_paras = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # if para too long > max_tokens*4 chars (~1600)
            if len(para) > max_tokens*4:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                expanded_paras.extend(sentences)
            else:
                expanded_paras.append(para)

        # Now build chunks by grouping paragraphs until token limit, respecting boundaries
        current_chunk = []
        current_len = 0
        for para in expanded_paras:
            para_len = len(para.split())  # approx tokens = words
            ctype = detect_content_type(para, heading)
            # equation boundary: if para is equation-like, keep as separate chunk
            if ctype == "equation" and len(para)<300:
                # flush current
                if current_chunk:
                    text = "\n\n".join(current_chunk)
                    chunks.append(_make_chunk(text, heading, heading_hierarchy, page_num, chunk_idx, section_type))
                    chunk_idx+=1
                    # overlap: keep last paragraph
                    overlap_text = current_chunk[-1] if len(current_chunk)>=1 else ""
                    current_chunk = [overlap_text] if overlap_text and overlap else []
                    current_len = len(overlap_text.split()) if overlap_text else 0
                # equation as its own chunk
                chunks.append(_make_chunk(para, heading, heading_hierarchy, page_num, chunk_idx, "equation"))
                chunk_idx+=1
                continue

            if current_len + para_len > max_tokens and current_chunk:
                # flush
                text = "\n\n".join(current_chunk)
                chunks.append(_make_chunk(text, heading, heading_hierarchy, page_num, chunk_idx, detect_content_type(text, heading)))
                chunk_idx+=1
                # overlap: keep last para(s) for continuity
                overlap_chunk = current_chunk[-1:] if len(current_chunk)>=1 else []
                current_chunk = overlap_chunk + [para]
                current_len = sum(len(p.split()) for p in current_chunk)
            else:
                current_chunk.append(para)
                current_len += para_len

        if current_chunk:
            text = "\n\n".join(current_chunk)
            chunks.append(_make_chunk(text, heading, heading_hierarchy, page_num, chunk_idx, detect_content_type(text, heading)))
            chunk_idx+=1

    # if no sections or still few chunks, fallback: page-level chunking
    if not chunks and pages:
        for p in pages:
            txt = p.get("text","").strip()
            if not txt:
                continue
            # split page into chunks
            paras = re.split(r"\n\s*\n", txt)
            cur = []
            cur_len=0
            for para in paras:
                para=para.strip()
                if not para: continue
                l=len(para.split())
                if cur_len + l > max_tokens and cur:
                    chunks.append(_make_chunk("\n\n".join(cur), f"Page {p['page_number']}", f"Page {p['page_number']}", p['page_number'], chunk_idx, "paragraph"))
                    chunk_idx+=1
                    cur=[para]
                    cur_len=l
                else:
                    cur.append(para)
                    cur_len+=l
            if cur:
                chunks.append(_make_chunk("\n\n".join(cur), f"Page {p['page_number']}", f"Page {p['page_number']}", p['page_number'], chunk_idx, "paragraph"))
                chunk_idx+=1

    # post-process: ensure each chunk has metadata
    for i, ch in enumerate(chunks):
        ch["chunk_index"]=i
        ch["char_count"]=len(ch["text"])
        ch["token_count"]=len(ch["text"].split())

    return chunks

def _make_chunk(text: str, section: str, heading_hierarchy: str, page_number: int, idx: int, content_type: str):
    return {
        "text": text.strip(),
        "section": section,
        "heading_hierarchy": heading_hierarchy,
        "page_number": page_number,
        "chunk_index": idx,
        "content_type": content_type,
    }

# Simple naive fixed-length baseline for tests/comparison (not used in production)
def naive_fixed_chunk(text: str, chunk_size: int = 500, overlap: int = 50):
    words = text.split()
    chunks=[]
    i=0
    idx=0
    while i < len(words):
        chunk_words=words[i:i+chunk_size]
        chunks.append({"text":" ".join(chunk_words), "chunk_index": idx, "content_type":"paragraph", "page_number":1, "section":"naive", "heading_hierarchy":"naive"})
        idx+=1
        i+=chunk_size-overlap
    return chunks
