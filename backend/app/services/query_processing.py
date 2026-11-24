import re
import unicodedata

# STEM tokens that must be preserved verbatim
STEM_PROTECT_PATTERNS = [
    r"ΔT", r"ΔV", r"Δt", r"Δ", r"η", r"μ", r"Ω", r"λ", r"θ",
    r"P\s*=\s*VI", r"P\s*=\s*V\s*I", r"V\s*=\s*I\s*R", r"Q\s*=\s*mcΔT", r"V\s*=\s*S\s*ΔT",
    r"TEC1-12706", r"pH", r"PM2\.5", r"kg/m³", r"kg/m\^3", r"W/mK",
    r"\d+\s*[mµn]?V", r"\d+\s*[Kk]Ω", r"\d+\s*W", r"\d+\s*%", r"\d+\s*K",
]

# Compile protected tokens regex - capture them to avoid normalizing
PROTECTED_RE = re.compile(r"(" + "|".join(STEM_PROTECT_PATTERNS) + r")", re.IGNORECASE)

def preserve_stem_tokens(query: str) -> tuple[str, dict]:
    """Replace protected tokens with placeholders, return (processed, map)"""
    placeholders = {}
    def repl(m):
        token = m.group(0)
        key = f"__STEM_{len(placeholders)}__"
        placeholders[key] = token
        return key
    protected = PROTECTED_RE.sub(repl, query)
    return protected, placeholders

def restore_stem_tokens(text: str, placeholders: dict) -> str:
    for k,v in placeholders.items():
        text = text.replace(k, v)
    return text

def normalize_query(query: str) -> str:
    """
    Query normalization for v0.2:
    - whitespace normalization
    - punctuation normalization (but preserve scientific punctuation)
    - basic token normalization lowercasing except STEM
    - equation/unit preservation
    """
    if not query:
        return ""
    original = query
    # Step 1 preserve STEM tokens
    protected, placeholders = preserve_stem_tokens(query)
    # Step 2 unicode normalization
    protected = unicodedata.normalize("NFKC", protected)
    # Step 3 whitespace normalization
    protected = re.sub(r"\s+", " ", protected).strip()
    # Step 4 punctuation normalization: collapse repeated punctuation but keep = / etc for equations
    # Don't strip = / * + - that are part of equations (already protected)
    # Normalize quotes, dashes
    protected = protected.replace("’", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    # Lowercase non-protected parts - we have placeholders uppercase, so lowercase then restore
    # Lowercase protected text but placeholders remain uppercase to restore case correctly
    lower = protected.lower()
    # Restore STEM tokens with original case
    restored = restore_stem_tokens(lower, {k.lower(): v for k,v in placeholders.items()})
    # For placeholders that were lowercased, restore
    # placeholders keys are __stem_0__ lowercased -> __stem_0__ ; we stored lowercased mapping
    # Actually placeholders keys were __STEM_0__ upper, after lower becomes __stem_0__, so need to map
    # Do second restore with lower keys
    # Also ensure we preserve original STEM case: use original tokens
    # Simpler: restore using lowercased keys
    for lk, v in {k.lower(): v for k,v in placeholders.items()}.items():
        restored = restored.replace(lk, v)
    # Final: strip and ensure not empty
    restored = re.sub(r"\s+", " ", restored).strip()
    # If query was mostly STEM tokens, ensure they are preserved with spaces
    # Remove excessive punctuation at ends
    restored = restored.strip(" .,;:")

    # Keep original equation forms if present: if original had "P = VI" preserve spacing
    # Already preserved via placeholders, but we lowercased surrounding text
    return restored if restored else original.strip()

def tokenize_preserve(query: str) -> list[str]:
    """Tokenize while preserving STEM tokens as single tokens"""
    normalized = normalize_query(query)
    # Split but keep placeholders? Already restored, so just split
    # Use regex that keeps STEM tokens together
    tokens = re.findall(r"__STEM_\d+__|ΔT|P\s*=\s*VI|V\s*=\s*IR|\w+[\w/-]*|[\W]", normalized)
    # Filter
    tokens = [t.strip() for t in tokens if t.strip() and t.strip() not in [",",".",";"]]
    return tokens
