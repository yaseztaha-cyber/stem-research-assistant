# End-to-End Value Table — v0.5

Controlled conditions: same 100 cases where stated, same relevance labels,
top_k=5. Retrieval-only metrics from strict 100-case benchmarks; human
scores are consensus means (1–5) over graded cases.

## Main table (mock generator)

| System | Retrieval Recall@5 | Human Correctness | Human Relevance | Human Completeness | Human Grounding | Avg Latency |
|---|---:|---:|---:|---:|---:|---:|
| TF-IDF + Simple + Mock (v3 prompt) | 0.947 | 3.17→1.84* | 3.25→2.22* | 3.08→1.71* | 3.33→2.51* | ~127 ms |
| Dense + CE + Mock (v3 prompt) | 0.953 | — (pairwise only) | — | — | — | ~2900 ms |

\* n=12 sample → n=100 full set. The drop reflects the harder full
distribution (49 system-proposed table/contradiction/derived cases where the
mock template fails), not a regression: the same 12 cases score identically.

## Real-LLM rows

| System | Retrieval | Human scores | Latency | Tokens | Status |
|---|---|---|---|---|---|
| TF-IDF + Real LLM (OpenAI-compat) | — | — | — | — | NOT RUN: no API key, no local endpoint (strict refusal verified) |
| Dense + Real LLM (OpenAI-compat) | — | — | — | — | NOT RUN: same reason |
| TF-IDF + LocalHF (SmolLM2-135M) | 0.947 config | not graded (pilot failed quality bar) | ~25–48 s/answer | ~1600–1650 total | PILOT ONLY (n=6, automated metrics) |
| Dense + LocalHF (SmolLM2-135M) | 0.953 config | not graded (pilot failed quality bar) | ~25–48 s/answer | ~1600–1650 total | PILOT ONLY (n=6, automated metrics) |

Local-HF pilot automated groundedness (6-case sample): mock 0.658–0.701 vs
local 0.620–0.649 — nearly identical despite local outputs being visibly
non-answers (fake URLs, prompt echo, ">10^9 K" physics nonsense). This
demonstrates automated groundedness can be gamed by vocabulary overlap and
must not substitute for human judgment.

Local pilot outputs are preserved in `docs/evaluation/local-ab-results.json`
(slim records). They were excluded from human grading because grading
rambling non-answers yields no signal beyond "tiny model fails" — documented
here instead of hidden.

## Pairwise retrieval-contrast (same mock generator, blinded, n=30)

Question: does better evidence produce better answers?

| Outcome | Count |
|---|---|
| Tie (no discernible difference) | 19 |
| Dense-evidence answer preferred | 7 |
| TF-IDF-evidence answer preferred | 4 |

When answers differ (11/30), dense evidence wins 7–4, but 63% ties show
retrieval differences rarely move the mock generator. Retrieval gains do not
reliably reach the answer with this generator.

## Cost/quality tradeoff (measured)

- Dense retrieval: +0.006 Recall@5, +0.069 MRR for +2775 ms latency and
  ~183 MB models. No API cost (local). Token cost N/A (mock).
- Cross-encoder: +0.04 MRR for +519 ms (TF-IDF path).
- Local-HF generation: ~1650 tokens/answer, ~25–48 s on CPU, cost unavailable
  (local compute). Quality: unusable at 135M scale for grounded RAG prompts.
- OpenAI-compatible path: implemented with usage capture
  (prompt/completion/total tokens, latency, cost="unavailable" unless the
  provider returns pricing — never invented). Not run: no credentials.

Conclusion: with the mock generator, the best measured system remains
TF-IDF + Simple (127 ms). Dense+CE is justified only for precision-critical
use. The generator — not retrieval — is the binding constraint on
human-rated quality.
