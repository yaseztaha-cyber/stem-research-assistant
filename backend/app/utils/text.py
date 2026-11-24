import re

HEADING_PATTERNS = [
    re.compile(r"^(Abstract|Introduction|Background|Methods|Methodology|Experimental Setup|Results|Discussion|Conclusion|References|Acknowledgments|Appendix|Objective|Materials|Procedure|Calculations|Questions|Sources of Error|Safety Information)\s*$", re.IGNORECASE),
    re.compile(r"^\d+(\.\d+)*\s+[A-Z][A-Za-z0-9\s\-:]{3,80}$"),
    re.compile(r"^[A-Z][A-Z\s]{5,80}$"),  # ALL CAPS headings
]

SECTION_MAP = {
    "abstract": "abstract",
    "introduction": "introduction",
    "background": "background",
    "methods": "methods",
    "methodology": "methods",
    "experimental setup": "experimental_setup",
    "results": "results",
    "discussion": "discussion",
    "conclusion": "conclusion",
    "references": "references",
    "objective": "objective",
    "materials": "materials",
    "procedure": "procedure",
    "calculations": "calculations",
    "safety": "safety",
}

def detect_section_type(heading: str) -> str | None:
    if not heading:
        return None
    low = heading.lower().strip()
    for k,v in SECTION_MAP.items():
        if k in low:
            return v
    return "general"

EQUATION_REGEXES = [
    re.compile(r"\$[^$]{3,80}\$"),
    re.compile(r"\\\[.*?\\\]"),
    re.compile(r"\\\(.*?\\\)"),
    re.compile(r"\b([A-Za-z]\s*=\s*[^=\n]{2,60})"),  # V = IR etc
    re.compile(r"P\s*=\s*V\s*I\b"),
    re.compile(r"V\s*=\s*I\s*R\b"),
    re.compile(r"E\s*=\s*m\s*c\^2"),
    re.compile(r"ΔT|\\Delta T"),
    re.compile(r"η\s*=\s*"),
]

TABLE_HINTS = ["Table ", "|", "\t", "  "]

def is_heading(line: str) -> bool:
    if not line or len(line)>120:
        return False
    stripped = line.strip()
    if len(stripped.split())>12:
        return False
    for pat in HEADING_PATTERNS:
        if pat.match(stripped):
            return True
    # heading often short and title case
    if len(stripped)<60 and stripped.endswith(":"):
        return True
    return False

def extract_equations(text: str):
    eqs = []
    for pat in EQUATION_REGEXES:
        for m in pat.finditer(text):
            candidate = m.group().strip()
            if len(candidate)>3 and len(candidate)<200:
                eqs.append(candidate)
    # dedupe
    seen=set()
    uniq=[]
    for e in eqs:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq

# Known variables explanation map (STEM common)
VARIABLE_MAP = {
    "V": ("voltage", "V", "volts"),
    "I": ("current", "A", "amperes"),
    "R": ("resistance", "Ω", "ohms"),
    "P": ("power", "W", "watts"),
    "E": ("energy", "J", "joules"),
    "Q": ("heat", "J", "joules"),
    "T": ("temperature", "K or °C", "kelvin/celsius"),
    "ΔT": ("temperature difference", "K", "kelvin"),
    "ΔV": ("voltage difference", "V", "volts"),
    "η": ("efficiency", "% or dimensionless", "percent"),
    "m": ("mass", "kg", "kilograms"),
    "c": ("specific heat capacity", "J/(kg·K)", "joules per kg kelvin"),
    "S": ("Seebeck coefficient", "V/K", "volts per kelvin"),
}

def explain_variables(equation_text: str):
    vars_found = {}
    for var, (meaning, unit, desc) in VARIABLE_MAP.items():
        # look for var as standalone letter (with word boundaries) or symbol
        if var in equation_text:
            # check boundary for single letters
            if len(var)==1:
                if re.search(rf"\b{re.escape(var)}\b", equation_text):
                    vars_found[var]={"meaning": meaning, "unit": unit, "description": desc}
            else:
                vars_found[var]={"meaning": meaning, "unit": unit, "description": desc}
    return vars_found
