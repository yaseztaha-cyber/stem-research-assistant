import sys
sys.path.insert(0, ".")
from backend.app.services.retrieval import keyword_score, cosine_similarity

def test_keyword_score():
    query = "electrical power equation"
    text = "Power: P = V * I defines electrical power"
    score = keyword_score(query, text)
    assert score > 0.3
    # no overlap should be low
    assert keyword_score("quantum", "thermoelectric heat engine") < 0.2

def test_cosine():
    a = [1,0,0]
    b = [1,0,0]
    assert cosine_similarity(a,b) == 1.0
    assert cosine_similarity([1,0],[0,1]) == 0.0
    assert cosine_similarity([], [1,0]) == 0.0

def test_hybrid_retrieval_integration():
    import backend.app.models.all_models
    from backend.app.database import SessionLocal
    from backend.app.services.retrieval import retrieve
    db = SessionLocal()
    # after seeding demo data, retrieval should return something
    results = retrieve(db, "Seebeck effect", top_k=3)
    assert len(results) >= 1
    # check hybrid scores present
    for r in results:
        assert "vector_score" in r
        assert "keyword_score" in r
        assert "score" in r
        assert r["score"] >= 0

if __name__ == "__main__":
    test_keyword_score()
    test_cosine()
    test_hybrid_retrieval_integration()
    print("retrieval tests passed")
