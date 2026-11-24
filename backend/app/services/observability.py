import time
import logging
import uuid
from functools import wraps
from typing import Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("stem-assistant")

# redact sensitive keys before logging
SENSITIVE_KEYS = {"api_key","openai_api_key","secret","password","token"}

def redact(data: Dict) -> Dict:
    if not isinstance(data, dict):
        return data
    out={}
    for k,v in data.items():
        if any(s in k.lower() for s in SENSITIVE_KEYS):
            out[k]="***REDACTED***"
        else:
            out[k]=v
    return out

def log_request(request_id: str, user_id: str, document_id: str, endpoint: str, latency: Dict, model: str, retrieved_chunks: int, error: str = None):
    payload = {
        "request_id": request_id or str(uuid.uuid4()),
        "user_id": user_id or "anon",
        "document_id": document_id or "none",
        "endpoint": endpoint,
        "retrieval_latency_ms": latency.get("retrieval_ms") if latency else None,
        "llm_latency_ms": latency.get("llm_ms") if latency else None,
        "embedding_latency_ms": latency.get("embedding_ms") if latency else None,
        "retrieved_chunks": retrieved_chunks,
        "model_used": model,
        "error": error,
    }
    # never log API keys or sensitive document contents unnecessarily
    logger.info(f"REQUEST {redact(payload)}")
    return payload
