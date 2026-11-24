# Error Analysis — v0.4 (100 cases)

## Summary (100 cases, TFIDF+Simple)

- Total cases: 100
- Cases with Recall@5 < 1.0: 7 (5 partial, 2 total Recall 0)
- Overall: Recall@5 0.947, Precision@5 0.65, MRR 0.85, NDCG@5 0.868

## End-to-end error taxonomy

| Category | Meaning |
|---|---|
| query classification | wrong query_type → wrong metadata hints |
| retrieval | correct evidence never in candidates |
| reranking | correct candidate demoted by reranker |
| evidence sufficiency | correct doc but not the specific row/value |
| context construction | evidence present but truncated/misordered in context |
| LLM reasoning | evidence present, answer wrong (mock template limits) |
| citation | citation doesn't support claim |
| grounding | unsupported claims in answer |
| answer relevance | correct facts, doesn't answer question |
| numerical reasoning | arithmetic/derivation wrong |
| equation reasoning | wrong equation selected |
| table extraction | table chunk missing/mis-tagged |
| source conflict | disagreement not surfaced |

## v0.2 known failures — resolution status

### Failure #1: "What efficiency was reported at ΔT=120K?" (was Recall 0.667, wrong_section)

Full trace (TFIDF+Simple, v0.4):

```text
query → "What efficiency was reported at ΔT=120K?"
query_type: experimental_result, metadata_hint {content_type: result, section: Results}
candidates: 26 → filtered → rerank (simple, query-type-aware)
rank 1: p.4 table (Results table DeltaT|V|I|P) score 0.879 rerank 1.012
rank 2: p.1 notes equation (5.2% at that point) score 0.552
final context → answer contains 5.2% with citation
```

- Root cause (v0.2): notes chunk (5.2% + 14% keywords) outranked Results table on keyword score.
- Fix: table/equation content-type boosts + query-type-aware reranker (+0.10 for result/table on experimental_result queries). No documents deleted, no hard filters.
- Result: rank 1 is now p.4 table. **RESOLVED.** Validated: overall Recall@5 stable 0.947 (no regression on other 99).

### Failure #2: "What procedure was used to measure TEG performance?" (was Recall 0.333, reranker_failure)

Full trace (v0.4):

```text
query → query_type: methodology, hint {section: Methods, content_type: procedure}
pre-rerank: lab-manual Procedure 0.82, paper Conclusion 0.681, paper p.3 Procedure 0.672
post-rerank (simple, query-type-aware): lab-manual 1.018, Conclusion 0.866, p.3 0.857
rank 3 = expected p.3 (load resistance) → Recall@5 = 1 (present)
```

- Root cause: abstract phrase overlap ("measure TEG") vs methodology evidence. Pre-rerank rank 3, post-rerank still rank 3: the query-type-aware reranker (+0.10 Methods/Procedure sections, +0.06 procedure type, −0.06 Abstract) narrowed the gap (0.82→1.018 vs 0.672→0.857) but did not promote p.3 above lab-manual/Conclusion.
- Why not boosted further: a larger boost would overfit this case and demote legitimate abstract answers for definition queries. Validated on full benchmark instead.
- Result: **IMPROVED** (expected chunk in top-5, Recall 1 for page-3 relevance) but MRR for this case remains 0.333. Cross-encoder (real, not fallback) was tested: same rank 3 — the abstract's exact phrase "measure TEG performance" genuinely matches. Documented mechanism, not weight-tuned away.

## Current failures (100-case run)

| Question | Expected | Retrieved | Recall | Failure type | Taxonomy |
|---|---|---|---|---|---|
| Calculate power if V=3.3V and I=1.27A | p.4 | [4,1,1,1,1] | 0.5 | partial | evidence sufficiency (table row present rank 1, derived value needs calculation) |
| What is the largest DeltaT tested? | p.4 | [1,5,2,4,1] | 0.667 | partial | retrieval (120K in many docs, rank 4) |
| Provide APA citation for the thermoelectric paper | p.6 | [2,1,4,1,5] | 0.0 | wrong_page | retrieval (References section p.6 not ranked; citation queries lack section hint) |
| Why does normalized 14% differ from raw 33%? | p.4 | [4,1,1,1,2] | 0.667 | partial | evidence sufficiency (heat-loss sentence rank-dependent) |
| Do dataset efficiencies match paper 5.2%? | p.1 | [4,6,1,5,2] | 0.333 | partial | source conflict (dataset vs paper values differ; correctly surfaces disagreement) |
| What long-term effect is not evaluated? | p.6 | [1,2,1,1,1] | 0.0 | wrong_page | retrieval (Future-work conclusion p.6 missed; research_gap hint weak) |
| What is 5.2 percent as a decimal? | p.4 | [1,4,6,1,1] | 0.667 | partial | numerical reasoning (0.052 never in corpus; requires derivation) |

## Retrieval vs Answer analysis (key distinction)

Inspected 12 graded answers (see human-gold-set.json):

| Case | Retrieval | Evidence | Citation | Answer | Human relevance |
|---|---|---|---|---|---|
| Power equation (P=VI) | PASS | PASS | PASS | PASS (after v0.4 equation-priority fix; before: FAIL "T=120K") | 5/5 |
| Seebeck effect | PASS | PASS | PARTIAL (cites lab-manual safety) | PARTIAL (generic) | 3/5 |
| Ohm's law | PASS | PASS | PASS | PASS (after *-strip fix) | 5/5 |
| Temp gradient effect | PASS | PARTIAL | PASS | FAIL (matched-load digression) | 2/5 |
| Efficiency equation | PASS | PASS | PASS | FAIL (returns V=S instead of Pout/Pin) | 2/5 |
| Improvement 14% | PASS | PASS | PASS | PASS | 4/5 |
| Max power 4.2W | PASS | PASS | PASS | FAIL (truncated "20...") | 2/5 |
| Materials Bi2Te3 | PASS | PARTIAL | PASS | FAIL (direct gives efficiency def; Bi2Te3 only in supporting) | 2/5 |
| Procedure | PASS | PASS | PASS | FAIL (direct "1") | 2/5 |

Pattern: **retrieval PASS but answer FAIL** in 5/12 — the RAG system finds evidence but the mock template LLM fails to use it (wrong snippet selection, truncation). This is the largest error source (LLM reasoning), not retrieval. Dense+CE cannot fix it; only a stronger generator (OpenAI LLM) or template overhaul would. Reported honestly: retrieval 0.947 vs human correctness mean 3.1/5.

## Recommendations (evidence-based, not applied blindly)

1. Citation queries: add `references` section hint (would fix APA case) — low risk, affects 2/100 cases.
2. Research-gap queries: boost Conclusion/Discussion sections — validate on full benchmark first.
3. Derived numeric answers (0.052): route through SymPy derivation path ([DERIVED]) rather than retrieval — already partially implemented.
4. Mock template: snippet selection now keyword+number aware (v0.4 fixes); further gains need real LLM.
