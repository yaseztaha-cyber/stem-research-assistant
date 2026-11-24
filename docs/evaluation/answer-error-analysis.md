# Answer-Error Analysis — v0.5 (retrieval-PASS / answer-FAIL)

Every case below had retrieval Recall@5 = 1 (correct evidence present) but a
low human score. Root causes classified per taxonomy.

## Root-cause counts (100 graded mock answers)

| Root cause | Cases | Example |
|---|---|---|
| Wrong snippet selection | ~25 | Citation questions answering "1"/"3"; dataset questions answering unrelated text |
| Missing derivation | ~12 | "P = VI" returned instead of computing 5.25% / 10W / 41860J |
| Truncation/fragment | ~8 | "20\nThe electrical output…" cut mid-sentence; single-char answers |
| Spurious conflict footer | ~40 answers affected | "power values differ: 4.2W, 3.14W" appended to citation/dataset questions; the contradiction detector fires on any differing %/W values even within one document |
| Generic opener, no direct value | ~20 | "This paper investigates…" for value questions (Seebeck unit, 210 uV/K, 0.052) |
| Correct | ~15 | Efficiency definition, cool-down step, future work, Seebeck equation |

## Notable cases

- "Calculate efficiency if Pout is 4.2W and Pin is 80W" → answer "P = VI" + spurious conflict. The mock calculation branch only handles V/I patterns; Pout/Pin values are ignored. Root cause: reasoning (no general value extraction).
- "What is 5.2 percent as a decimal?" → generic intro. Requires derivation (0.052), mock has no decimal-conversion path. Root cause: numerical reasoning.
- "Provide APA citation…" → "1 [SOURCE: lab-manual]". The citation *generator* (`citations.py`) was never invoked by the mock; it answered from retrieval text. Root cause: instruction following (wrong subtask).
- "Do dataset efficiencies match…?" → conflict note cites "25.0%/50.0%" — dataset column *statistics* misread as efficiency values. Root cause: context selection (dataset overview stats leak into conflict detection).
- "What happens to P if V doubles…" → correct DERIVED answer. The one derived-reasoning success: pattern-matched branch.

## Local-model pilot (6 cases, excluded from grading)

Typical outputs: fabricated citation metadata ("Dr. John Smith… University of
California… URL"), prompt echo, table fragments, ">10^9 K" nonsense.
Root cause: 135M model cannot follow long grounded prompts; greedy decoding
degenerates. Lesson: minimum viable real generator for this task is far above
135M, or prompts must be far shorter. Preserved in `local-ab-results.json`.

## What this implies

Fixing retrieval further cannot fix the ~25 wrong-snippet cases (evidence was
already present) — only generation-side changes can: value-aware snippet
selection, general SymPy substitution from query values, invoking the citation
generator for citation queries, and gating the conflict footer on
cross-document same-metric conflicts (currently over-triggers intra-document).
These are documented, not silently patched into the benchmark, to preserve
v0.5 comparability.
