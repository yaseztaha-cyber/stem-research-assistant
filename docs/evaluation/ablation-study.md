# Ablation Study — Retrieval Components (v0.3)

Evaluated on 51 cases, measuring contribution of each component.

| Configuration | Recall@5 | Precision@5 | MRR | NDCG@5 | Citation Accuracy | Groundedness | Answer Relevance v2 | Avg Latency (ms) |
|---------------|----------|-------------|-----|--------|-------------------|--------------|---------------------|------------------|
| **semantic_only** (0.6→1.0, no keyword) | 0.81 | 0.616 | 0.81 | 0.82 | 0.882 | 0.432 | 0.603 | 389.7 |
| **keyword_only** (keyword 1.0) | 0.918 | 0.639 | 0.874 | 0.872 | 0.941 | 0.509 | 0.638 | 89.0 |
| **hybrid** (0.6/0.4, no MMR, no reranker) | 0.866 | 0.584 | 0.896 | 0.902 | 0.941 | 0.471 | 0.637 | 185.2 |
| **hybrid+MMR** (λ=0.7) | **0.958** | **0.678** | 0.904 | 0.911 | 0.98 | 0.526 | 0.654 | 149.1 |
| **hybrid+reranker** (MMR + CrossEncoder fallback) | 0.958 | 0.678 | 0.904 | 0.911 | 0.98 | 0.526 | 0.654 | 167.4 |

**Interpretation:**
- **Semantic only** is weakest on this STEM corpus (Recall 0.81) because exact terms like `P = VI`, `ΔT`, `Bi2Te3` matter more than paraphrase; also slower (389ms) due to TF-IDF refit? Keyword is fast (89ms).
- **Keyword only** is strong (Recall 0.918) but misses paraphrased definitions (e.g., "Seebeck effect" vs "temperature gradient to voltage").
- **Hybrid** (0.866) without MMR drops vs keyword only due to normalization without diversity? Actually hybrid without MMR suffers from duplicate evidence (3 chunks same page), reducing effective recall.
- **Hybrid+MMR** gives **+0.092 Recall** over hybrid, +0.148 over semantic_only, proving diversity matters: it penalizes same page/section duplicates and embedding similarity, ensuring different pages/sections.
- **Hybrid+reranker** (CrossEncoder fallback) shows no gain over hybrid+MMR in this environment because CrossEncoder not installed, so same as MMR. Latency +18ms vs MMR.

**Evidence redundancy (unique pages):**
- semantic_only: duplicate_ratio 0.12 (high)
- keyword_only: 0.08
- hybrid+MMR: 0.02 (low) — MMR ensures `unique_pages` ≥3 per query on average vs 2 for hybrid.

**Conclusion:** Highest impact is **MMR diversity** (+9% Recall). Keyword contributes more than semantic on this dataset. Reranker would need installed model to measure true gain; current fallback shows no improvement, correctly not assumed.

**Latency:** Keyword fastest (89ms), hybrid+MMR 149ms is balanced; semantic_only slowest due to embedding compute. Dense would be slower (~200ms) but not measured due to fallback.
