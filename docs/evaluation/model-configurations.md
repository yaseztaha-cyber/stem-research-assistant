# Model Configurations — v0.4 (reproducibility)

Measured 2026-09-15 on Windows (win32, CPython 3.14.0, CPU-only torch).

| Component | Value |
|---|---|
| Python | 3.14.0 |
| torch | 2.14.0+cpu (cuda False) |
| sentence-transformers | 6.0.1 |
| scikit-learn | 1.9.0 |
| numpy | 2.4.6 |
| pandas | 3.0.3 |
| sympy | 1.14.0 |
| fastapi | 0.116.2 |
| sqlalchemy | 2.0.53 |
| Embedding model (dense) | sentence-transformers/all-MiniLM-L6-v2, dim 384 |
| Reranker model | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| TF-IDF | scikit-learn TfidfVectorizer, max_features 384, ngram (1,2), english stopwords |
| LLM | mock (deterministic template, no external API) |

## Resource use (local measurement)

| Item | Value |
|---|---|
| Dense model disk | 91.6 MB |
| Cross-encoder disk | 91.8 MB |
| Total model disk | 183.4 MB |
| Backend process RSS (idle, models unloaded) | ~514 MB |
| SQLite DB | 0.48 MB |
| Stored embeddings | 26 vectors |

Note: process RSS measured without loaded transformer models; first dense/CE query adds ~300–500 MB transient (CPU). Cold-start latencies include model load from local HF cache (no network after first download).

## Reproduction

```bash
pip install -r backend/requirements.txt  # includes sentence-transformers, torch (CPU)
python -m backend.app.services.evaluation preflight
python -m backend.app.services.evaluation matrix --strict
```

All benchmark runs in this report used: same documents, same chunking, same 100 evaluation cases, same relevance labels, top_k=5, same metric definitions. Dense chunk vectors recomputed on-the-fly so dense-vs-dense comparison is valid (stored vectors are TF-IDF from ingestion).
