from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import logging
import uuid

from .config import settings
from .database import init_db
from .api import documents, rag, learning, collections, analysis, conversations, evaluation, search, grading

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Source-grounded STEM Research Assistant with claim-level provenance, hybrid retrieval, and evidence verification.",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Observability middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.time()
    try:
        response = await call_next(request)
        latency = int((time.time()-start)*1000)
        logging.info(f"{request.method} {request.url.path} -> {response.status_code} [{latency}ms] rid={request_id}")
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as e:
        logging.exception(f"Unhandled error {request.url.path} rid={request_id}: {e}")
        return JSONResponse(status_code=500, content={"detail": "Internal error", "request_id": request_id})

@app.on_event("startup")
def on_startup():
    init_db()
    # seed evaluation cases if needed
    try:
        from .database import SessionLocal
        from .services.evaluation import seed_evaluation_cases
        db = SessionLocal()
        seed_evaluation_cases(db)
        db.close()
    except Exception as e:
        logging.warning(f"Seed failed: {e}")

# Routers
app.include_router(documents.router, prefix="/api")
app.include_router(rag.router, prefix="/api")
app.include_router(learning.router, prefix="/api")
app.include_router(collections.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(conversations.router, prefix="/api")
app.include_router(evaluation.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(grading.router, prefix="/api")

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": settings.app_version,
        "llm_provider": settings.llm_provider,
        "embedding_provider": settings.embedding_provider,
        "database": settings.database_url.split(":")[0],
    }

@app.get("/")
def root():
    return {"name": settings.app_name, "docs": "/docs", "health": "/api/health"}

# Global error handler for validation
@app.exception_handler(Exception)
async def general_exception(request: Request, exc: Exception):
    logging.exception(f"Exception at {request.url}: {exc}")
    return JSONResponse(status_code=500, content={"detail": str(exc)[:500]})
