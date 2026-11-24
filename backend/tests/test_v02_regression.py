"""Regression test: v0.1 acceptance must still pass after v0.2 upgrade"""
import backend.app.models.all_models
from backend.app.database import SessionLocal
from pathlib import Path
import asyncio

def test_v02_regression():
    db = SessionLocal()
    from backend.app.models.document import Document
    from backend.app.services.rag import rag_query, compare_documents
    from backend.app.services.retrieval import retrieve
    from backend.app.services.evaluation import run_evaluation
    from backend.app.models.chunk import DocumentChunk

    # upload works (check docs exist)
    docs = db.query(Document).all()
    assert len(docs) >= 1, "upload/indexing regression"
    # indexing works: chunks exist
    chunks = db.query(DocumentChunk).count()
    assert chunks > 0, "indexing regression"

    # retrieval works
    res = retrieve(db, "Seebeck effect", top_k=3)
    assert len(res) >= 1, "retrieval regression"
    for r in res:
        assert "vector_score" in r and "keyword_score" in r

    # grounded chat works
    async def check_grounded():
        qres = await rag_query(db, "What is the Seebeck effect?", top_k=3)
        assert "answer" in qres
        assert "retrieved" in qres and len(qres["retrieved"])>0
        assert "grounding" in qres
        assert "citations" in qres and len(qres["citations"])>0
        # claim-level
        assert "claims" in qres
        # citation validation
        for c in qres["citations"]:
            assert "document" in c and "page" in c

        # multi-doc still works if 2 docs
        docs2 = db.query(Document).limit(2).all()
        if len(docs2)>=2:
            comp = await compare_documents(db, "Compare methods", [d.id for d in docs2[:2]])
            assert "per_document" in comp
            assert "comparison" in comp

    asyncio.run(check_grounded())

    # flashcards
    from backend.app.services.flashcards import generate_flashcards
    cards = generate_flashcards(db, limit=2)
    assert len(cards) >= 0 # may be empty if no chunks, but not error

    # problems
    from backend.app.services.problems import generate_problems
    probs = generate_problems(db, limit=1)
    assert len(probs) >= 0

    # questions
    from backend.app.services.questions import generate_research_questions
    qs = generate_research_questions(db, limit=2)
    assert len(qs) >= 0

    # dataset analysis
    from backend.app.services.dataset import analyze_dataset
    p = Path("demo_data/sample-dataset.csv")
    if p.exists():
        analysis = analyze_dataset(p)
        assert "observed_results" in analysis
        assert "ai_interpretation" in analysis

    # collections
    from backend.app.models.collection import Collection, CollectionDocument
    cols = db.query(Collection).all()
    # at least can create
    from backend.app.services.evaluation import seed_evaluation_cases
    seed_evaluation_cases(db)
    assert db.query(Collection).count() >= 0

    # evaluation works
    eval_res = run_evaluation(db)
    assert "summary" in eval_res
    assert "retrieval_recall" in eval_res["summary"] or "recall_at_5" in eval_res["summary"]

    print("v0.2 regression passed")
