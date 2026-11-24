# Metric Validation vs Human Ratings — v0.5 (n=100)

Spearman ρ (ordinal human consensus means vs automated 0–1 scores).

| Automated metric | Human dimension | v0.4 (n=12) | v0.5 (n=100) |
|---|---|---|---|
| Answer Relevance v2 | human relevance | 0.391 | **0.168** |
| Answer Relevance v3 | human relevance | — | **0.024** |
| Answer Relevance v3 | human completeness | — | 0.158 |
| Groundedness | human grounding | 0.513 | **0.191** |
| Citation Accuracy | human citation | 0.000 | **0.168** |
| Question Coverage | human correctness | 0.457 | **0.120** |

## Reading

- v2 is WEAK (ρ=0.17), not validated. The n=12 moderate values were small-sample noise.
- v3 is WORSE (ρ=0.02) — a negative result, kept as evidence. Failure analysis: v3 strips pipeline conflict footers, but the mock hides required values *inside those footers*, so stripping destroys value coverage; v3's stricter directness collapses variance (most mock answers open generically). v3 remains experimental; **v2 stays the reported metric**.
- All automated metrics correlate weakly at n=100. Contributing causes: range restriction (human scores pile at 1–2 on hard cases), ceiling effects (citation accuracy ≈0.97 constant), and the synthetic-answer gap (evaluation's v2/v3 are computed on synthetic answers in `run_evaluation`, while humans grade generated answers — see prompt-ablation note).
- Per §20: no thresholds were tuned to improve these numbers. v3's components were fixed a priori (5% tolerance, fixed stemmer, fixed boilerplate list).

Recompute: `GET /api/grading/correlation`. Gold set: `docs/evaluation/human-gold-set.json` (100 cases, 30 double-graded, anonymized).
