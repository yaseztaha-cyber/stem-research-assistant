import re
from typing import Dict

# Symbolic validation using sympy where possible
try:
    import sympy
    from sympy.parsing.sympy_parser import parse_expr
    HAS_SYMPY = True
except ImportError:
    HAS_SYMPY = False

COMMON_EQUATIONS = {
    "P = VI": {"vars": {"P","V","I"}, "units": {"P":"W","V":"V","I":"A"}},
    "V = IR": {"vars": {"V","I","R"}, "units": {"V":"V","I":"A","R":"Ω"}},
    "Q = mcΔT": {"vars": {"Q","m","c","ΔT"}, "units": {"Q":"J","m":"kg","c":"J/kg·K","ΔT":"K"}},
    "V = S * DeltaT": {"vars": {"V","S","DeltaT"}, "units": {"V":"V","S":"V/K","DeltaT":"K"}},
}

def validate_equation_syntax(equation_text: str) -> Dict:
    if not HAS_SYMPY:
        # fallback regex syntax check
        if "=" not in equation_text or len(equation_text.strip())<3:
            return {"syntax_valid": False, "error": "no equals sign"}
        return {"syntax_valid": True, "parser": "regex_fallback"}
    try:
        # Split equation
        if "=" not in equation_text:
            return {"syntax_valid": False, "error": "no equals"}
        left, right = equation_text.split("=",1)
        # Parse both sides with sympy (replace Δ etc)
        left_clean = left.strip().replace("ΔT","DeltaT").replace("η","eta").replace("Δ","Delta")
        right_clean = right.strip().replace("ΔT","DeltaT").replace("η","eta").replace("Δ","Delta")
        # Replace ^ with **
        left_clean = left_clean.replace("^","**")
        right_clean = right_clean.replace("^","**")
        # Try parse
        l_expr = parse_expr(left_clean)
        r_expr = parse_expr(right_clean)
        vars_l = l_expr.free_symbols if hasattr(l_expr, 'free_symbols') else set()
        vars_r = r_expr.free_symbols if hasattr(r_expr, 'free_symbols') else set()
        vars_all = set([str(s) for s in vars_l.union(vars_r)])
        return {"syntax_valid": True, "variables": list(vars_all), "left": str(l_expr), "right": str(r_expr)}
    except Exception as e:
        return {"syntax_valid": False, "error": str(e)[:200]}

def check_variable_consistency(equation_text: str) -> Dict:
    vars_extracted = re.findall(r"\b[A-Za-z]\b", equation_text)
    # Check against common equations for consistency
    norm = re.sub(r"\s+", "", equation_text).lower().replace("*","")
    for known, info in COMMON_EQUATIONS.items():
        nk = re.sub(r"\s+", "", known).lower().replace("*","")
        if norm == nk:
            return {"consistent": True, "known_equation": known, "expected_vars": list(info["vars"])}
    return {"consistent": None, "note": "not in known library, check manually"}

def validate_substitution(equation_text: str, values: Dict[str, float]) -> Dict:
    """Check arithmetic via substitution if values provided"""
    if not HAS_SYMPY or not values:
        return {"checked": False, "reason": "sympy unavailable or no values"}
    try:
        left, right = equation_text.split("=",1)
        left_clean = left.strip().replace("ΔT","DeltaT").replace("^","**")
        right_clean = right.strip().replace("ΔT","DeltaT").replace("^","**")
        l_expr = parse_expr(left_clean)
        r_expr = parse_expr(right_clean)
        # Substitute
        subs = {parse_expr(k): v for k,v in values.items()}
        l_val = float(l_expr.subs(subs)) if hasattr(l_expr, 'subs') else None
        r_val = float(r_expr.subs(subs)) if hasattr(r_expr, 'subs') else None
        if l_val is not None and r_val is not None:
            diff = abs(l_val - r_val)
            return {"checked": True, "left_value": l_val, "right_value": r_val, "difference": diff, "consistent": diff < 1e-6}
    except Exception as e:
        return {"checked": False, "error": str(e)[:200]}
    return {"checked": False}

def dimensional_check(equation_text: str) -> Dict:
    # Simple dimensional check for common equations
    norm = re.sub(r"\s+", "", equation_text).lower()
    if "p=vi" in norm:
        return {"dimensionally_consistent": True, "explanation": "V·A = W correct [GENERATED]"}
    if "v=ir" in norm:
        return {"dimensionally_consistent": True, "explanation": "A·Ω = V correct"}
    if "q=mc" in norm:
        return {"dimensionally_consistent": True, "explanation": "kg·J/(kg·K)·K = J correct"}
    return {"dimensionally_consistent": None, "explanation": "unknown equation, manual check needed"}

def full_math_validation(equation_text: str, values: Dict[str,float] = None) -> Dict:
    syntax = validate_equation_syntax(equation_text)
    var_check = check_variable_consistency(equation_text)
    dim = dimensional_check(equation_text)
    subs = validate_substitution(equation_text, values or {})
    overall = syntax.get("syntax_valid", False) and (var_check.get("consistent") is not False)
    return {
        "equation": equation_text,
        "syntax": syntax,
        "variable_consistency": var_check,
        "dimensional": dim,
        "substitution": subs,
        "overall_valid": overall,
        "note": "Validation uses sympy where available; scientific validity requires domain review, not just parser acceptance [GENERATED]"
    }
