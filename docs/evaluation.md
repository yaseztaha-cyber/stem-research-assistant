# Evaluation

## Dataset

Seeded in `backend/app/services/evaluation.py`:

```python
[
  {"question": "What equation defines electrical power?", "expected": "P = VI", "page": 4},
  {"question": "What is the Seebeck effect?", "expected": "voltage from temperature difference", "page": 2},
  {"question": "What is Ohm's law?", "expected": "V = IR", "page": 3},
  {"question": "How does temperature gradient affect output?", "expected": "larger gradient increases voltage", "page": 6},
]
```

Extend via `EvaluationCase` table.

## Metrics

- **Retrieval Recall**: whether expected page is in top-k retrieved (1 if hit else 0)
- **Retrieval Precision**: hits / retrieved count
- **Citation Accuracy**: whether expected concept string appears in retrieved text
- **Groundedness**: grounding score (see grounding.md)
- **Unsupported Claim Rate**: unsupported source claims / total source claims
- **Answer Relevance**: avg term overlap query vs retrieved

## Running

```bash
curl http://localhost:8000/api/evaluation/run
# returns summary averages + per-case breakdown

pytest backend/tests/test_integration.py -v  # tests evaluation as integration
```

Example output:

```json
{
  "summary": {
    "total_cases": 4,
    "retrieval_recall": 0.75,
    "retrieval_precision": 0.3,
    "citation_accuracy": 0.75,
    "groundedness": 0.68,
    "unsupported_claim_rate": 0.1,
    "answer_relevance": 0.55
  },
  "cases": [ ... ]
}
```

Use to detect regressions when RAG pipeline changes. In CI, fail if recall drops >10% vs baseline.

## Regression Example

Question: "What equation defines electrical power?" Expected `P = VI` page 4. If retrieval no longer returns equation chunk (e.g., after changing chunk size), recall goes 1→0 and test fails.

## Future

Add MRR, NDCG, human eval for explanation quality, equation exact match.
