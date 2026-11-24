import re
import csv
import io
from pathlib import Path
from typing import List, Dict, Tuple
from pypdf import PdfReader

from ..utils.text import is_heading, detect_section_type, extract_equations, explain_variables

def parse_pdf(file_path: Path) -> Dict:
    reader = PdfReader(str(file_path))
    pages = []
    full_text = ""
    metadata = {}
    try:
        meta = reader.metadata
        if meta:
            metadata = {
                "title": getattr(meta, "title", None),
                "author": getattr(meta, "author", None),
                "subject": getattr(meta, "subject", None),
                "creator": getattr(meta, "creator", None),
                "producer": getattr(meta, "producer", None),
            }
            # clean Nones
            metadata = {k:v for k,v in metadata.items() if v}
    except Exception:
        pass

    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as e:
            text = f"[Extraction failed: {e}]"
        pages.append({"page_number": i, "text": text, "char_count": len(text)})
        full_text += text + "\n\n"

    # attempt to extract references section
    references = []
    if "References" in full_text:
        ref_section = full_text.split("References")[-1][:5000]
        refs = [l.strip() for l in ref_section.splitlines() if len(l.strip())>20]
        references = refs[:20]

    # detect document-level sections via headings scanning
    sections = detect_sections(pages)

    # tables heuristic: pages with many pipes/tabs
    # equations are extracted per page
    equations = []
    for p in pages:
        eqs = extract_equations(p["text"])
        for eq in eqs:
            equations.append({
                "page": p["page_number"],
                "equation_text": eq,
                "variables": explain_variables(eq),
                "context": p["text"][:500],
                "uncertain": False
            })

    return {
        "pages": pages,
        "metadata": metadata,
        "sections": sections,
        "equations": equations,
        "references": references,
        "full_text": full_text
    }

def detect_sections(pages: List[Dict]) -> List[Dict]:
    sections = []
    order = 0
    current_heading = "Introduction"
    heading_hierarchy = "Introduction"
    for p in pages:
        lines = p["text"].splitlines()
        buffer = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if is_heading(stripped):
                # flush previous
                if buffer:
                    sections.append({
                        "title": current_heading,
                        "level": 1,
                        "heading_hierarchy": heading_hierarchy,
                        "section_type": detect_section_type(current_heading),
                        "text": "\n".join(buffer),
                        "page_number": p["page_number"],
                        "order_index": order
                    })
                    order+=1
                    buffer=[]
                current_heading = stripped
                heading_hierarchy = stripped  # simplified
            else:
                buffer.append(stripped)
        if buffer:
            sections.append({
                "title": current_heading,
                "level": 1,
                "heading_hierarchy": heading_hierarchy,
                "section_type": detect_section_type(current_heading),
                "text": "\n".join(buffer),
                "page_number": p["page_number"],
                "order_index": order
            })
            order+=1
    if not sections and pages:
        # fallback one section per page
        for p in pages:
            sections.append({
                "title": f"Page {p['page_number']}",
                "level": 1,
                "heading_hierarchy": f"Page {p['page_number']}",
                "section_type": "general",
                "text": p["text"][:2000],
                "page_number": p["page_number"],
                "order_index": p["page_number"]
            })
    return sections

def parse_text_file(file_path: Path) -> Dict:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    # treat as one page per 2000 chars? but we keep pages as single
    pages = [{"page_number": 1, "text": text, "char_count": len(text)}]
    # markdown headings detection
    sections=[]
    order=0
    current="Document"
    hierarchy="Document"
    buffer=[]
    for line in text.splitlines():
        if line.strip().startswith("#"):
            if buffer:
                sections.append({"title": current, "level": 1, "heading_hierarchy": hierarchy, "section_type": detect_section_type(current), "text": "\n".join(buffer), "page_number":1, "order_index":order})
                order+=1
                buffer=[]
            current=line.strip().lstrip("#").strip()
            hierarchy=current
        else:
            buffer.append(line)
    if buffer:
        sections.append({"title": current, "level":1, "heading_hierarchy":hierarchy, "section_type":detect_section_type(current), "text":"\n".join(buffer), "page_number":1, "order_index":order})
    if not sections:
        sections=[{"title":"Document","level":1,"heading_hierarchy":"Document","section_type":"general","text":text[:4000],"page_number":1,"order_index":0}]
    eqs=[]
    for eq in extract_equations(text):
        eqs.append({"page":1,"equation_text":eq,"variables":explain_variables(eq),"context":text[max(0,text.find(eq)-200):text.find(eq)+500],"uncertain":False})
    return {"pages": pages, "metadata": {}, "sections": sections, "equations": eqs, "references": [], "full_text": text}

def parse_csv_file(file_path: Path) -> Dict:
    text = file_path.read_text(encoding="utf-8", errors="ignore")[:2000]
    # treat csv as dataset: also produce textual representation for chunks
    import pandas as pd
    try:
        df = pd.read_csv(file_path, nrows=1000)
        # dataset overview text
        overview = f"Dataset: {file_path.name}\nColumns: {', '.join(df.columns.tolist())}\nRows: {len(df)}\n\n"
        overview += df.head().to_string() + "\n\n"
        overview += df.describe(include='all').to_string()
        pages=[{"page_number":1, "text": overview, "char_count": len(overview)}]
        sections=[{"title":"Dataset Overview","level":1,"heading_hierarchy":"Dataset Overview","section_type":"results","text":overview,"page_number":1,"order_index":0}]
        return {"pages": pages, "metadata": {"columns": df.columns.tolist(), "rows": len(df)}, "sections": sections, "equations": [], "references": [], "full_text": overview, "dataframe": df}
    except Exception as e:
        txt = f"CSV parsing failed: {e}\nRaw:\n{text}"
        return {"pages": [{"page_number":1,"text":txt,"char_count":len(txt)}], "metadata": {}, "sections": [{"title":"Dataset","level":1,"heading_hierarchy":"Dataset","section_type":"general","text":txt,"page_number":1,"order_index":0}], "equations": [], "references": [], "full_text": txt}

def parse_document(file_path: Path, file_type: str) -> Dict:
    low = file_type.lower().lstrip(".")
    # Simple caching by file hash
    try:
        from .cache import document_cache
        import hashlib
        h = hashlib.md5(file_path.read_bytes()[:2000000]).hexdigest()
        cached = document_cache.get("document", {"path": str(file_path), "hash": h, "type": low})
        if cached:
            return cached
    except Exception:
        cached = None
        h = None

    result = None
    if low=="pdf":
        # Try layout-aware if configured
        try:
            from ..config import settings
            from ..core.document_parser import get_parser
            parser_name = getattr(settings, "document_parser", "pypdf")
            # Try advanced equation parser as well
            if parser_name == "layout_aware":
                result = get_parser("layout_aware").parse(file_path)
            else:
                result = parse_pdf(file_path)
                # Enhance with table/figure detection even with pypdf fallback via layout parser logic
                try:
                    from ..core.document_parser import LayoutAwarePDFParser
                    extra = LayoutAwarePDFParser().parse(file_path)
                    # Merge tables/figures if not already
                    if "tables" not in result:
                        result["tables"] = extra.get("tables", [])
                    if "figures" not in result:
                        result["figures"] = extra.get("figures", [])
                except Exception:
                    pass
        except Exception:
            result = parse_pdf(file_path)

        # Use advanced equation parser if configured
        try:
            from ..config import settings
            from ..core.equation_parser import get_equation_parser
            eq_parser_name = getattr(settings, "equation_parser", "advanced")
            eq_parser = get_equation_parser(eq_parser_name)
            # Re-extract equations with advanced parser for better latex/normalized
            adv_eqs = []
            for p in result.get("pages", []):
                adv_eqs.extend(eq_parser.extract(p["text"], page=p["page_number"], section=""))
            # Merge with existing, deduplicate
            existing = {e["equation_text"] for e in result.get("equations",[])}
            for eq in adv_eqs:
                if eq["equation_text"] not in existing:
                    # Map to old format for backward compat
                    result["equations"].append({
                        "page": eq["page"],
                        "equation_text": eq["equation_text"],
                        "variables": eq["variables"],
                        "context": eq["context"],
                        "uncertain": eq["uncertainty"],
                        "raw_expression": eq["raw_expression"],
                        "normalized_expression": eq["normalized_expression"],
                        "latex_expression": eq["latex_expression"],
                        "confidence": eq["confidence"],
                    })
        except Exception:
            pass
    elif low in ["txt","md","markdown"]:
        result = parse_text_file(file_path)
    elif low=="csv":
        result = parse_csv_file(file_path)
    else:
        result = parse_text_file(file_path)

    # Cache result
    try:
        if result is not None and h is not None:
            from .cache import document_cache
            document_cache.set("document", {"path": str(file_path), "hash": h, "type": low}, result, ttl=3600)
    except Exception:
        pass

    return result
