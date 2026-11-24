from abc import ABC, abstractmethod
from typing import List, Dict
import re

class EquationParser(ABC):
    @abstractmethod
    def extract(self, text: str, page: int = 1, section: str = "") -> List[Dict]:
        pass
    @property
    @abstractmethod
    def name(self) -> str:
        pass

class RegexEquationParser(EquationParser):
    @property
    def name(self) -> str:
        return "regex"
    def extract(self, text: str, page: int = 1, section: str = "") -> List[Dict]:
        from ..utils.text import extract_equations, explain_variables
        eqs = extract_equations(text)
        result = []
        for eq in eqs:
            result.append({
                "raw_expression": eq,
                "normalized_expression": re.sub(r"\s+", "", eq).lower().replace("*",""),
                "latex_expression": eq,  # fallback same as raw
                "equation_text": eq,
                "variables": explain_variables(eq),
                "units": None,
                "uncertainty": False,
                "confidence": 0.95,
                "page": page,
                "section": section,
                "context": text[max(0, text.find(eq)-200): text.find(eq)+300][:500],
                "parser": self.name
            })
        return result

class AdvancedEquationParser(EquationParser):
    """Advanced parser with better normalization, LaTeX handling, and uncertainty detection"""
    @property
    def name(self) -> str:
        return "advanced"
    def extract(self, text: str, page: int = 1, section: str = "") -> List[Dict]:
        from ..utils.text import explain_variables
        # Regex + LaTeX
        patterns = [
            re.compile(r"\$[^$]{2,120}\$"),
            re.compile(r"\\\[.*?\\\]"),
            re.compile(r"\\\(.*?\\\)"),
            re.compile(r"\b([A-Za-zημΔ]\s*=\s*[A-Za-z0-9ΔημΩ\*\s\/\+\-\.\^\(\)]{2,60})"),
            re.compile(r"P\s*=\s*V\s*\*?\s*I\b"),
            re.compile(r"V\s*=\s*I\s*\*?\s*R\b"),
        ]
        found = []
        seen = set()
        for pat in patterns:
            for m in pat.finditer(text):
                raw = m.group().strip()
                if len(raw)<4 or len(raw)>150:
                    continue
                # Clean LaTeX delimiters
                cleaned = raw.strip("$").strip(r"\[").strip(r"\]").strip()
                # Detect uncertainty due to OCR artifacts
                uncertain = "?" in cleaned or "�" in raw or cleaned.count("_")>3
                norm = re.sub(r"\s+", "", cleaned).lower().replace("*","")
                latex = cleaned  # preserve
                if cleaned not in seen:
                    seen.add(cleaned)
                    found.append({
                        "raw_expression": raw,
                        "normalized_expression": norm,
                        "latex_expression": latex,
                        "equation_text": cleaned,
                        "variables": explain_variables(cleaned),
                        "units": None,
                        "uncertainty": uncertain,
                        "confidence": 0.7 if uncertain else 0.92,
                        "page": page,
                        "section": section,
                        "context": text[max(0, text.find(raw)-200): text.find(raw)+300][:500],
                        "parser": self.name
                    })
        return found

def get_equation_parser(prefer: str = "regex") -> EquationParser:
    if prefer == "advanced":
        return AdvancedEquationParser()
    return RegexEquationParser()
