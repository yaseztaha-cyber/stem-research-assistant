# AI STEM Research Assistant — Source-Grounded RAG System

> **A source-grounded STEM research and learning system with claim-level provenance, hybrid retrieval, evidence verification, structured scientific reasoning, and measurable RAG evaluation.**

Not "a chatbot that reads PDFs" — a research workspace where every factual claim is traceable to its source page/section/chunk, and AI-generated interpretation is explicitly labeled.

> **v0.2 improves retrieval, evidence verification, citation validation, and measurable RAG evaluation while preserving a lightweight local-first architecture.**  
> Baseline v0.1: Recall 0.50, Precision 0.113, Citation Accuracy 0.50 → **v0.2: Recall@5 0.96 (+0.46), Precision@5 0.52 (+0.407), Citation Accuracy 1.00 (+0.50), MRR 0.836, NDCG@5 0.874** on 25 cases. See `docs/evaluation/v0.2-report.md` and `docs/evaluation/v0.1-baseline.json`.

---

## Project Overview

Students and researchers upload PDF textbooks, research papers, lab manuals, markdown notes, and CSV datasets. The system parses structure, chunks intelligently, embeds with a pluggable provider, retrieves via hybrid vector + BM25 + metadata filtering, and generates answers that distinguish **SOURCE-DERIVED** from **MODEL-GENERATED** information. Claims carry provenance `{document_id, document_name, page_number, section, chunk_id, source_text, retrieval_score, citation_metadata}`.

Supported outputs: Concept Explanations (4 levels), Key Equations with variable/unit explanation, Evidence Explorer, Research Questions (8 categories), Flashcards (10 types), Practice Problems (with unit verification), Citations (APA/IEEE/MLA), Dataset Analysis, Paper/Lab Manual analysis, Multi-document comparison.

## Architecture

```
Document → Ingestion → Parsing (pypdf + heuristics) → Structure detection → Chunking (structure-aware) → Embeddings (TF-IDF/OpenAI) → Retrieval (hybrid) → Evidence verification → LLM (mock/OpenAI) → Structured outputs
```

**Stack**
- **Backend**: FastAPI 0.115, SQLAlchemy 2, SQLite (production: Postgres ready), Pydantic v2, Alembic migrations
- **Frontend**: Vite + React 18 + TypeScript + Tailwind CSS (scientific clean language, no purple gradients)
- **Parsing**: `pypdf` + custom heading/section/equation/table detection preserving page/heading hierarchy
- **Embeddings**: Pluggable `EmbeddingProvider` — `TfidfEmbeddingProvider` (offline, default) + `DenseEmbeddingProvider` (all-MiniLM-L6-v2, local, fallback) + `OpenAIEmbeddingProvider` via `EMBEDDING_PROVIDER`
- **LLM**: Pluggable `LLMProvider` — `MockLLMProvider` (deterministic) + `OpenAIProvider`
- **Vector DB**: Abstraction `VectorStore` → `SQLiteVectorStore` (default, no external DB) + `Qdrant`/`PgVector` placeholders; hybrid + MMR + reranking via `SimpleReranker`/`CrossEncoderReranker` (`RERANKER_PROVIDER`)
- **Observability**: request_id, retrieval/LLM latency, model used, grounding factors

See [docs/architecture.md](docs/architecture.md) and mermaid diagrams there.

## Features

- **Source-Grounded Mode** (strict): refuses to hallucinate, labels [SOURCE] vs [GENERATED], shows conflict when sources disagree
- **Claim-level provenance**: every claim linked to evidence with document/page/section/chunk and "Open source context" viewer
- **Intelligent chunking**: respects heading, paragraph, equation, table, page boundaries; overlap within same section
- **Hybrid retrieval**: TF-IDF vector (60%) + BM25-style keyword (40%) + metadata filtering (document, page, section, content_type) + reranker
- **Grounding score**: not a single number — stores `retrieval_relevance, evidence_coverage, claim_source_alignment, contradiction_handled, source_quality, unsupported_claim_rate`
- **Equation engine**: regex extraction, variable/unit explanation, uncertainty flagging
- **Learning engines**: flashcards, problems (with dimensional/arithmetic validation), research questions categorized
- **Dataset analysis**: overview, missing values, distributions, correlations, anomalies, distinguishes observed vs AI interpretation
- **Paper/Lab modes**: auto-detects Abstract/Methods/Results etc., extracts objective/methodology/variables/safety prominently
- **Collections + multi-doc reasoning**: compare Paper A vs Paper B evidence side-by-side
- **Global search**: across chunks, equations, flashcards, questions, docs (semantic + exact)
- **Citations**: APA/IEEE/MLA from real metadata, never fabricates missing fields
- **Evaluation**: automated metrics — Retrieval Recall/Precision, Citation Accuracy, Groundedness, Unsupported Claim Rate

## Tech Stack Table

| Layer | Choice | Reason |
|-------|--------|--------|
| API | FastAPI | Async, auto docs, Pydantic |
| DB | SQLite + SQLAlchemy | Zero-config demo, migratable to Postgres |
| Embeddings | TF-IDF (default) | Works offline, no API key needed |
| Retrieval | Custom hybrid | No external vector DB required |
| PDF | pypdf + ReportLab (demo gen) | Pure python, no system deps |
| Frontend | Vite React TS + Tailwind | Fast, clean scientific UI |

## Installation

```bash
# backend
cd backend
pip install -r requirements.txt
cp .env.example .env   # set OPENAI_API_KEY if you want OpenAI provider
# database auto-creates on first run: storage/app.db

# frontend
cd ../frontend
npm install
```

## Environment Variables

| Var | Default | Description |
|-----|---------|-------------|
| `SECRET_KEY` | dev-secret | JWT/API signing |
| `DATABASE_URL` | sqlite:///../storage/app.db | SQLAlchemy URL |
| `LLM_PROVIDER` | mock | `mock` or `openai` |
| `OPENAI_API_KEY` | — | Required for openai provider |
| `OPENAI_MODEL` | gpt-4o-mini | |
| `EMBEDDING_PROVIDER` | tfidf | `tfidf` / `openai` |
| `RETRIEVAL_TOP_K` | 8 | |
| `VITE_API_URL` | http://localhost:8000 | Frontend proxy target |

Never commit `.env`. See `backend/.env.example`.

## Database Setup

```bash
# auto-migration on startup via init_db()
python -c "from backend.app.database import init_db; init_db()"
# or with alembic (if configured)
alembic upgrade head
```

Tables: `users, documents, document_pages, document_sections, document_chunks, embeddings, equations, collections, collection_documents, conversations, messages, claims, evidence, citations, flashcards, practice_problems, research_questions, evaluation_cases`

## Document Pipeline

1. **Upload** — validated file type/size, path traversal protection, safe filename
2. **Parse** — PDF: text + page numbers + headings + tables + equations + references; TXT/MD: markdown headings; CSV: pandas overview + textual chunk
3. **Chunk** — structure-aware, `content_type` tagging (paragraph/equation/table/definition/procedure/result/discussion/reference)
4. **Embed** — batched via provider, L2-normalized, stored as JSON
5. **Index** — ready for hybrid retrieval

Structure: `Document → Pages → Sections → Paragraphs/Equations/Tables → References`

## RAG Architecture

```
User Query → Query preprocessing → Semantic (TF-IDF cosine) + Keyword (BM25) → Candidate ranking (weighted 0.6/0.4) → Reranker (phrase/term/type boosts) → Top-k → Context construction (structured SOURCE blocks) → LLM (mock/openai with system prompt treat sources as DATA) → Claim extraction → Evidence matching → Unsupported detection → Citation verification → Final answer
```

See `docs/rag.md` for hybrid scoring formulas.

## Grounding System

- **Two classes**: SOURCE-DERIVED (`[SOURCE]`) vs MODEL-GENERATED (`[GENERATED]`)
- **Claim-level**: each sentence classified; evidence linked via term overlap + retrieval scores
- **Rules**: no invented facts, no fabricated page numbers/equations, insufficient evidence fallback, conflict identification
- **Score**: weighted `0.25*retrieval + 0.35*coverage + 0.2*alignment + 0.1*contradiction + 0.1*quality - unsupported_penalty`

See `docs/grounding.md`.

## Citation System

- Generates APA/IEEE/MLA from `document.doc_metadata` (authors, title, journal, year, DOI, etc.)
- Preserves `Metadata unavailable` instead of fabricating
- Provenance stored per citation: document, page, section, chunk_id, source_text, retrieval_score

See `docs/citations.md`.

## Evaluation

```bash
# seed demo cases
curl -X POST http://localhost:8000/api/evaluation/seed
# run
curl http://localhost:8000/api/evaluation/run
# or pytest
pytest backend/tests -v
```

Metrics: `Retrieval Recall, Retrieval Precision, Citation Accuracy, Groundedness, Unsupported Claim Rate, Answer Relevance`. Evaluation dataset includes questions like "What equation defines electrical power?" with expected_source_page=4.

See `docs/evaluation.md`.

## Testing

```bash
pytest backend/tests -v          # 13 tests: chunking, grounding, retrieval, dataset, equations, integration
# unit: chunking, metadata extraction, citation generation, equation parsing, dataset stats, claim classification
# integration: upload→parse→index, query→retrieval→generation, citation→evidence, multi-doc
# evaluation: grounding, citation accuracy, unsupported claims
```

## Security

- Input validation, file type/size limits (50MB), safe file handling, path traversal protection (`get_safe_path`), prompt-injection awareness (sources wrapped as DATA, system prompt forbids following instructions in sources, `is_prompt_injection_attempt` detection), API key protection (redacted logs), document isolation per user/collection.

See `docs/security.md`.

## Limitations

- PDF extraction via `pypdf` loses figures/images; tables as text only; equations via regex so complex LaTeX may be marked uncertain
- TF-IDF embeddings are lightweight; for production use `sentence_transformers` or OpenAI embeddings (swap via env)
- Mock LLM is deterministic templating; for nuanced reasoning set `OPENAI_API_KEY`
- Dataset analysis limited to CSV; no Excel/Parquet yet; correlations only numeric
- No user auth UI (backend User model ready, endpoints can be added)

## Future Improvements

- Replace TF-IDF with `BGE-M3` or `text-embedding-3-large` + Qdrant/pgvector
- OCR for scanned PDFs (`pymupdf` + `tesseract`)
- LaTeX equation renderer (MathJax) + sympy validation
- Full auth (JWT) + document sharing/permissions
- Streaming answers + websocket for long queries
- Alembic migrations versioned
- Frontend: virtualized evidence list, full markdown equation rendering

## How to Run the Complete Application

```bash
# 1. Backend
cd "stem research ai"
pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8000
# -> http://localhost:8000/docs (OpenAPI)

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev
# -> http://localhost:5173

# 3. Try workflow:
# - Drag demo_data/thermoelectric-paper.pdf into upload zone (Processing → Parsed → Indexed → Ready)
# - Select document, ask "Explain the main mechanism." → see citations with page/section, click to open context
# - Ask "What equation defines electrical power?" → retrieve P=VI with variable explanation
# - Generate flashcards / practice problems / research questions
# - Upload second source (lab-manual.md), create collection "Thermoelectric Energy Project", add both, ask "Compare the experimental methods." → see Paper A evidence vs Paper B evidence + AI interpretation, conflict handling
# - Upload demo_data/sample-dataset.csv, click Dataset → Analysis distinguishes observations from AI interpretation
# - Check Evaluation tab or GET /api/evaluation/run — measurable RAG quality
```

Demo data: `demo_data/thermoelectric-paper.pdf` (6 pages, reportlab-generated, legal sample), `thermoelectric-notes.md`, `lab-manual.md`, `sample-dataset.csv` (12 rows, DeltaT/V/I/P).

## API Overview

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/documents/upload | upload document |
| POST | /api/documents/{id}/analyze-dataset | analyze CSV |
| GET | /api/documents | list docs |
| GET | /api/documents/{id}/chunks | chunks |
| GET | /api/documents/{id}/equations | equations |
| POST | /api/rag/query | RAG with grounding, claim-level provenance |
| POST | /api/rag/explain | concept explanation by level |
| POST | /api/rag/compare | multi-doc comparison |
| POST | /api/learning/flashcards | generate flashcards |
| POST | /api/learning/problems | practice problems |
| POST | /api/learning/questions | research questions |
| GET | /api/learning/citations/{doc_id} | APA/IEEE/MLA |
| GET | /api/analysis/paper/{id} | paper mode |
| GET | /api/analysis/lab/{id} | lab manual mode |
| GET | /api/search | global search |
| GET | /api/evaluation/run | evaluation metrics |
| GET | /api/health | health check |

---

**Engineering quality focus**: correctness, traceability, maintainability, testability, security, clear architecture — not file count. All features are real; no fake retrieval, citations, or confidence scores. When external model unavailable: "AI provider unavailable. Your documents are still available locally."
