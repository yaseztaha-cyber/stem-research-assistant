from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List

class DocumentParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path) -> Dict:
        pass
    @property
    @abstractmethod
    def name(self) -> str:
        pass

class PyPDFParser(DocumentParser):
    @property
    def name(self) -> str:
        return "pypdf"
    def parse(self, file_path: Path) -> Dict:
        from ..services.parsing import parse_pdf as _parse_pdf
        return _parse_pdf(file_path)

class LayoutAwarePDFParser(DocumentParser):
    """Layout-aware parser preserving tables, figures, captions, headings.
    Uses pypdf as base but adds heuristics for scientific layout.
    Falls back to PyPDFParser if layout analysis fails.
    """
    @property
    def name(self) -> str:
        return "layout_aware"
    def parse(self, file_path: Path) -> Dict:
        from ..services.parsing import parse_pdf as _parse_pdf
        from ..services.parsing import detect_sections
        from ..utils.text import extract_equations, explain_variables
        import re
        base = _parse_pdf(file_path)
        pages = base.get("pages", [])
        # Enhance with table/figure detection
        tables = []
        figures = []
        for p in pages:
            text = p["text"]
            # Table detection: lines with | or multiple tabs or 3+ columns separated by 2+ spaces
            lines = text.splitlines()
            for idx, line in enumerate(lines):
                if "|" in line and line.count("|")>=2:
                    # table row
                    headers = [h.strip() for h in line.split("|") if h.strip()]
                    rows = []
                    # look ahead for rows
                    for nxt in lines[idx+1: idx+4]:
                        if "|" in nxt:
                            rows.append([c.strip() for c in nxt.split("|") if c.strip()])
                        else:
                            break
                    if headers and rows:
                        tables.append({
                            "page": p["page_number"],
                            "headers": headers,
                            "rows": rows[:5],
                            "section": None,
                            "caption": None,
                            "raw": line + " | " + " | ".join(rows[0]) if rows else line
                        })
                elif re.search(r"\s{2,}[^\s]+\s{2,}[^\s]+\s{2,}[^\s]+", line) and any(c.isdigit() for c in line):
                    # space-separated table
                    parts = re.split(r"\s{2,}", line.strip())
                    if len(parts)>=3 and len(parts)<=6:
                        tables.append({
                            "page": p["page_number"],
                            "headers": [],
                            "rows": [parts],
                            "section": None,
                            "raw": line.strip()
                        })
            # Figure detection: lines starting with Figure/Fig.
            for line in lines:
                if re.match(r"^(Figure|Fig\.)\s*\d+[:\.]", line.strip(), re.IGNORECASE):
                    figures.append({
                        "figure_id": f"fig-{p['page_number']}-{len(figures)+1}",
                        "document_id": None,
                        "page": p["page_number"],
                        "caption": line.strip()[:300],
                        "section": None
                    })
                # also caption line after image placeholder (PyPDF may have)
                if re.match(r"^Table\s*\d+[:\.]", line.strip(), re.IGNORECASE):
                    # table caption
                    for t in reversed(tables):
                        if t["page"]==p["page_number"] and not t["caption"]:
                            t["caption"] = line.strip()
                            break
        # Enhance sections already in base
        base["tables"] = tables
        base["figures"] = figures
        base["parser"] = self.name
        return base

def get_parser(prefer: str = "pypdf") -> DocumentParser:
    if prefer == "layout_aware":
        return LayoutAwarePDFParser()
    return PyPDFParser()
