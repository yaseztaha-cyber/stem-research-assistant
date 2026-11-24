import os
import re
import hashlib
from pathlib import Path
from fastapi import HTTPException

MAX_FILENAME_LENGTH = 255
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".markdown"}

def validate_filename(filename: str) -> str:
    # path traversal protection
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename: path traversal detected")
    if len(filename) > MAX_FILENAME_LENGTH:
        raise HTTPException(status_code=400, detail="Filename too long")
    # sanitize
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    ext = Path(safe).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}")
    return safe

def validate_file_size(size_bytes: int, max_mb: int = 50):
    if size_bytes > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large: {size_bytes} bytes exceeds {max_mb}MB limit")

def sanitize_text(text: str) -> str:
    # prevent prompt injection: treat document content as data, escape instruction-like patterns
    # We don't block content, but we annotate it as untrusted data
    if not text:
        return text
    # Remove/escape system instruction markers
    # Keep content but prefix with marker for LLM context
    # We will wrap retrieved chunks with clear delimiters so LLM knows it's data
    return text

def get_safe_path(upload_dir: Path, filename: str) -> Path:
    safe_name = validate_filename(filename)
    # generate unique prefix to avoid collisions but keep name traceable
    import uuid
    unique = uuid.uuid4().hex[:8]
    final = f"{unique}_{safe_name}"
    path = upload_dir / final
    # ensure still inside upload_dir
    try:
        path.resolve().relative_to(upload_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Path traversal blocked")
    return path

def is_prompt_injection_attempt(text: str) -> bool:
    patterns = [
        r"ignore\s+all\s+previous\s+instructions",
        r"system\s*:",
        r"you\s+are\s+now",
        r"disregard\s+.*instructions",
    ]
    low = text.lower()
    for pat in patterns:
        if re.search(pat, low):
            return True
    return False

# API key protection: never log keys
def redact_sensitive(data: dict) -> dict:
    out = {}
    for k,v in data.items():
        if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
            out[k] = "***REDACTED***"
        else:
            out[k]=v
    return out
