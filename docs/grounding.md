# Grounding System

## Principle

> Every important factual statement must be traceable to a source, while the system must clearly distinguish source-derived information from AI-generated explanations.

## Two Classes

- **SOURCE-DERIVED**: directly supported by uploaded sources. Stored with `document_id, document_name, page_number, section, chunk_id, source_text, retrieval_score, citation_metadata`. Examples: "According to the uploaded paper...", "The equation on page 8 states..."

- **MODEL-GENERATED**: simplified explanations, analogies, connections, additional examples, interpretation, study advice, generated problems. Labeled `[GENERATED]`, never presented as from source.

## Claim-Level Provenance

Do not merely list sources at bottom; attach per claim:

```
The experiment increased electrical output by approximately 14%. [SOURCE]
→ {type: "source", document: "experiment.pdf", page: 7, section: "Results", chunk_id: "..."}
```

```
This can be understood as the system converting a larger temperature gradient into a larger thermoelectric voltage. [GENERATED]
```

UI: clicking `[Citation]` shows Document/Page/Section/Original Context + retrieval score + why classification happened (term overlap, retrieval relevance).

## Grounding Rules (when Source-Grounded Mode enabled)

1. Do not invent facts and attribute to source.
2. If insufficient evidence: "The supplied sources do not provide enough evidence to answer this confidently."
3. Separate SUPPORTED vs AI interpretation with labels.
4. Never fabricate page numbers, equations, quotations, results, citations, metadata.
5. If evidence conflicts, explicitly identify: "Source A reports X. Source B reports Y. The sources therefore disagree."

Implemented via system prompt + post-processing checks.

## Confidence / Grounding Score

Not mathematical truth; system confidence from:

- retrieval relevance (avg top-3 scores)
- evidence coverage (source claims with term overlap >0.25)
- claim-source alignment
- contradiction detection (multiple percentages, explicit conflict markers)
- source quality (peer-reviewed 0.9, etc.)
- unsupported claim rate

Store factors, not just number:

```json
{
  "score": 0.82,
  "percentage": 82,
  "factors": {
    "retrieval_relevance": 0.85,
    "evidence_coverage": 0.9,
    "claim_source_alignment": 0.85,
    "contradiction_handled": 0.9,
    "source_quality": 0.85,
    "unsupported_claim_rate": 0.1,
    "total_claims": 5,
    "source_claims": 3,
    "generated_claims": 2
  }
}
```

Formula: `score = 0.25*retrieval +0.35*coverage +0.2*alignment +0.1*contradiction +0.1*quality - 0.3*unsupported_rate`

## Pipeline

```
Generated Answer
  ↓ Claim extraction (sentence split, [SOURCE]/[GENERATED] heuristics)
  ↓ Evidence matching (term overlap vs retrieved chunks)
  ↓ Unsupported claim detection (source claims with no evidence)
  ↓ Citation verification (citation patterns exist, match retrieved doc/pages)
  ↓ Contradiction detection (conflicting numbers, explicit disagreement markers)
  ↓ Final answer (if unsupported_rate>0.4 add disclaimer; if no evidence return insufficient message)
```

## Hallucination Protection

Checks: retrieval relevance, claim-source alignment, citation existence/validity, contradiction detection, unsupported claim detection. If a claim cannot be supported in grounded mode, label as generated or state insufficient evidence.

See `backend/app/services/grounding.py`.
