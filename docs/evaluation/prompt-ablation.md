# Prompt / Generation Ablation — v0.5 (mock, TFIDF+Simple, 100 cases)

Each arm adds exactly one component. Automated metrics on generated (not
synthetic) answers.

| Arm | +Component | Answer v2 | Answer v3 | Groundedness | Citation pass |
|---|---|---|---|---|---|
| P1 basic (v1+flat, no validation) | — | 0.479 | 0.375 | 0.739 | — |
| P2 query structure (v2+flat) | query formats | 0.479 | 0.375 | 0.739 | — |
| P3 evidence hierarchy (v2+optimized) | context ordering | 0.466 | 0.313 | 0.649 | — |
| P4 answer plan (v3+optimized) | internal plan | 0.466 | 0.313 | 0.649 | — |
| P5 validation (v3+optimized+val) | post-gen labels | 0.466 | 0.313 | 0.649 | — |

Raw: `docs/evaluation/prompt-ablation-results.json`.

## Interpretation (honest null results included)

- P1 = P2 exactly: the mock parses only Query-Type/Length markers, so format
  guides don't move it. Query-specific templates are designed for real
  generators; with mock they are inert by construction.
- P3/P4 = P5: the answer plan is internal-only and validation annotations
  rarely trigger on brief answers — no measurable effect with mock.
- P1/P2 vs P3+: optimized context scores *slightly lower* (v2 −0.013,
  groundedness −0.09). Cause: reordering changes which source the mock's
  first-snippet heuristic picks. This is a mock artifact, not evidence that
  evidence ordering harms real generators.
- Conclusion: with the mock generator, no prompt component shows a gain.
  Prompt ablations must be re-run against a capable real LLM; the harness
  (`generation_experiment.py`, `prompt_version` param) is ready for that.

Human pairwise for prompt versions was deliberately NOT run: the automated
ablation shows mock outputs are near-invariant across prompt versions, so 15
blinded judgments would mostly confirm ties. Stated here instead of spending
grader effort to manufacture a finding.
