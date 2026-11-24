# Retrieval Configuration Comparison — v0.4 (100 cases, strict, no fallback)

All configs: same documents, same chunking, same 100 evaluation cases, same labels, top_k=5. Strict mode: any fallback → FAILED with no score. All four configs genuinely loaded (fallback=false). Dense chunk vectors recomputed on-the-fly (stored vectors are TF-IDF).

| Configuration | Recall@5 | Precision@5 | MRR | NDCG@5 | Citation Acc | Groundedness | Unsupported | Legacy Rel | Answer Rel v2 | Avg Lat | P95 Lat | Cold Start |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TFIDF+Simple | 0.947 | 0.650 | 0.850 | 0.868 | 0.97 | 0.523 | 0.05 | 0.351 | 0.609 | 126.8 ms | 166 ms | 5099 ms |
| TFIDF+CrossEncoder | 0.933 | 0.672 | 0.892 | 0.900 | 0.96 | 0.546 | 0.06 | 0.370 | 0.608 | 646.2 ms | 837 ms | 38799 ms |
| Dense+Simple | 0.942 | 0.680 | 0.892 | 0.895 | 0.97 | 0.556 | 0.04 | 0.318 | 0.610 | 2161.6 ms | 2651 ms | 37883 ms |
| Dense+CrossEncoder | 0.953 | 0.702 | 0.919 | 0.921 | 0.97 | 0.554 | 0.04 | 0.338 | 0.610 | 2902.3 ms | 3741 ms | 51933 ms |

Active identity (all fallback=false):
- TFIDF+Simple: requested tfidf/simple → active tfidf/simple
- TFIDF+CrossEncoder: requested tfidf/cross_encoder → active tfidf/cross_encoder (cross-encoder/ms-marco-MiniLM-L-6-v2 loaded: YES)
- Dense+Simple: requested dense/simple → active dense/simple (all-MiniLM-L6-v2 loaded: YES)
- Dense+CrossEncoder: requested dense/cross_encoder → active dense/cross_encoder (both loaded: YES)

## Reading

- Best retrieval: Dense+CrossEncoder (Recall 0.953, MRR 0.919, NDCG 0.921) — but only +0.006 recall / +0.069 MRR over TFIDF+Simple at 23× latency (2902 vs 127 ms).
- Dense alone (Dense+Simple recall 0.942) does NOT beat TFIDF+Simple (0.947). Dense helps only combined with CE, modestly.
- Cross-encoder alone (TFIDF+CE): precision/MRR up slightly, recall slightly down (0.933), 5× latency.
- Answer Relevance v2 is flat (0.608–0.610) across all configs: retrieval gains do not reach the answer (mock LLM bottleneck).
- Citation Accuracy flat 0.96–0.97; Groundedness 0.52–0.56.
- Cold start includes model load from local cache (5s TFIDF init … 52s both transformers); warm P95 is the steady-state number to use.

## Recommendation

Default stays TFIDF+Simple (127 ms, Recall 0.947). Dense+CE is opt-in for precision-critical use where 2.9 s/query is acceptable. Do not assume Dense+CrossEncoder superior — measured.
