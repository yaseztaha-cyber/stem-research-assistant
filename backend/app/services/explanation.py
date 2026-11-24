from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from .retrieval import retrieve, build_rag_context
from ..core.llm_provider import get_global_llm

LEVELS = {
    "beginner": "Explain simply, avoid jargon, use analogies, define every term.",
    "intermediate": "Assume high-school STEM background, include mechanism and simple example.",
    "advanced": "Assume undergraduate STEM, include mathematical formulation, derivations, nuances.",
    "research": "Assume researcher level, discuss open questions, limitations, conflicting evidence, and precise formalism."
}

TEMPLATE = """You are a STEM explanation engine. Structure response as:
Definition
Intuition
Mechanism
Mathematical formulation (if applicable, with variables/units)
Example
Common mistakes
Source evidence (with citations)

Levels: {level} - {level_desc}
Query: {concept}
Context:
{context}

Rules: Do not invent equations. If source has equations, explain variables/units. Distinguish source vs generated.
If no equation in sources, say "No equation found in sources" rather than inventing.
Label claims with [SOURCE] and [GENERATED].
"""

async def explain_concept(db: Session, concept: str, level: str = "intermediate", document_ids=None, collection_id=None):
    level_desc = LEVELS.get(level, LEVELS["intermediate"])
    retrieved = retrieve(db, concept, top_k=6, document_ids=document_ids, collection_id=collection_id)
    context = build_rag_context(retrieved) if retrieved else "No source context available."
    prompt = TEMPLATE.format(level=level, level_desc=level_desc, concept=concept, context=context)
    llm = get_global_llm()
    answer = await llm.generate(prompt, system="You are a helpful STEM tutor that distinguishes source vs generated. Never fabricate equations.")
    # If retrieved empty, prepend notice
    if not retrieved:
        answer = "> The supplied sources do not provide enough evidence to answer this confidently. [GENERATED]\n\n" + answer
    return {
        "concept": concept,
        "level": level,
        "explanation": answer,
        "sources": retrieved,
        "structure": ["Definition","Intuition","Mechanism","Mathematical formulation","Example","Common mistakes","Source evidence"]
    }
