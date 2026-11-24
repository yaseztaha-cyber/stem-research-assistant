from sqlalchemy.orm import Session
from typing import List, Dict
import re
from ..models.equation import Equation
from ..utils.text import explain_variables

# Known equations library for enrichment (not fabrication; only for variable explanation)
COMMON_EQUATIONS = {
    "V = IR": {"meaning": "Ohm's Law", "variables": {"V": "voltage (V)", "I": "current (A)", "R": "resistance (Ω)"}},
    "P = VI": {"meaning": "Electrical power", "variables": {"P": "power (W)", "V": "voltage (V)", "I": "current (A)"}},
    "P = I^2 R": {"meaning": "Power dissipation", "variables": {}},
    "E = mc^2": {"meaning": "Mass-energy equivalence", "variables": {}},
    "Q = mcΔT": {"meaning": "Heat transfer", "variables": {"Q": "heat (J)", "m": "mass (kg)", "c": "specific heat (J/kg·K)", "ΔT": "temperature difference (K)"}},
    "η = Pout / Pin": {"meaning": "Efficiency", "variables": {"η": "efficiency", "Pout": "output power", "Pin": "input power"}},
    "V = S ΔT": {"meaning": "Seebeck voltage", "variables": {"V": "voltage", "S": "Seebeck coefficient (V/K)", "ΔT": "temperature gradient (K)"}},
}

def extract_equations_from_text(text: str, page: int, section: str):
    # regex already used in parsing, here for API search
    import re
    patterns = [r"[A-Za-z]\s*=\s*[^=\n]{2,80}", r"P\s*=\s*V\s*I", r"V\s*=\s*I\s*R", r"η\s*=\s*[^ \n]+", r"S\s*=\s*[^ \n]+"]
    found=[]
    for pat in patterns:
        for m in re.finditer(pat, text):
            eq = m.group().strip()
            if 3 < len(eq) < 120:
                found.append({"equation_text": eq, "page": page, "section": section, "variables": explain_variables(eq)})
    return found

def list_equations(db: Session, document_id: str = None, search: str = None) -> List[Dict]:
    q = db.query(Equation)
    if document_id:
        q = q.filter(Equation.document_id==document_id)
    eqs = q.all()
    result=[]
    for e in eqs:
        data = {"id": e.id, "document_id": e.document_id, "page": e.page_number, "section": e.section, "equation_text": e.equation_text, "variables": e.variables, "units": e.units, "context": e.context, "uncertain": e.uncertain, "confidence": e.confidence}
        if search and search.lower() not in e.equation_text.lower():
            continue
        result.append(data)
    return result

def explain_equation(db: Session, equation_id: str):
    e = db.query(Equation).filter(Equation.id==equation_id).first()
    if not e:
        return None
    vars_explained = e.variables or explain_variables(e.equation_text)
    # enrich with common knowledge but label as generated if not in source
    # ensure we distinguish source vs generated
    explanation_parts = []
    explanation_parts.append(f"**Equation:** `{e.equation_text}` [SOURCE]")
    explanation_parts.append(f"**Found on:** Page {e.page_number}, Section: {e.section} [SOURCE]")
    if e.context:
        explanation_parts.append(f"**Context:** {e.context[:300]} [SOURCE]")
    explanation_parts.append("**Variables:** [GENERATED interpretation of symbols]")
    for var, meta in (vars_explained or {}).items():
        explanation_parts.append(f"- `{var}` = {meta.get('meaning','?')} [{meta.get('unit','')}]")
    # detect common equation meaning
    for known, info in COMMON_EQUATIONS.items():
        if known.replace(" ","") in e.equation_text.replace(" ",""):
            explanation_parts.append(f"**Recognition:** This matches {info['meaning']} (common form {known}) [GENERATED]")
            break
    if e.uncertain:
        explanation_parts.append("> ⚠️ Extraction uncertain due to OCR/formatting; verify against original document. [GENERATED]")
    return {"equation": e.equation_text, "explanation": "\n".join(explanation_parts), "variables": vars_explained, "uncertain": e.uncertain}
