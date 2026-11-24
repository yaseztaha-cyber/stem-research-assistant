import sys
sys.path.insert(0, ".")
import backend.app.models.all_models
from backend.app.database import SessionLocal, init_db
from pathlib import Path
import asyncio

def test_full_pipeline():
    db = SessionLocal()
    # upload -> parse -> index already done via demo seed, test query -> retrieval -> generation -> citation
    from backend.app.services.rag import rag_query
    async def run():
        result = await rag_query(db, "What is the Seebeck voltage equation? Explain variables.", top_k=4)
        assert "answer" in result
        assert "retrieved" in result
        assert len(result["retrieved"]) >= 1
        assert "grounding" in result
        assert result["grounding"]["score"] >= 0
        # citation verification
        assert len(result["citations"]) >= 1
        # check answer contains source-derived vs generated distinction
        ans_low = result["answer"].lower()
        assert "[source" in ans_low or "source" in ans_low

        # test multi-document comparison
        from backend.app.models.document import Document
        docs = db.query(Document).limit(2).all()
        if len(docs)>=2:
            from backend.app.services.rag import compare_documents
            comp = await compare_documents(db, "Compare experimental methods", [d.id for d in docs[:2]])
            assert "per_document" in comp
            assert "comparison" in comp

        # test evidence explorer
        from backend.app.services.retrieval import retrieve
        ev = retrieve(db, "Seebeck", top_k=2)
        assert ev[0]["page_number"] is not None

        # test evaluation
        from backend.app.services.evaluation import run_evaluation
        eval_res = run_evaluation(db)
        assert "summary" in eval_res
        assert "retrieval_recall" in eval_res["summary"]

    asyncio.run(run())
    print("integration passed")

if __name__ == "__main__":
    test_full_pipeline()
