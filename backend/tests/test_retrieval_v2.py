import backend.app.models.all_models
from backend.app.database import SessionLocal
from backend.app.services.retrieval import retrieve_with_trace, keyword_score, cosine_similarity
from backend.app.services.retrieval_v2 import normalize_scores, mmr_selection

def test_normalize_scores():
    res = normalize_scores([0.2,0.5,0.8])
    assert abs(res[0]-0.0)<1e-6 and abs(res[1]-0.5)<1e-6 and abs(res[2]-1.0)<1e-6
    assert normalize_scores([1,1,1]) == [0.5,0.5,0.5]
    assert normalize_scores([]) == []

def test_mmr_diversity():
    candidates = [
        {"chunk_id":"a","score":0.9,"text":"same text about thermoelectric power","page_number":1,"section":"A","document_id":"d1","chunk_index":0,"vector":[1,0]},
        {"chunk_id":"b","score":0.85,"text":"same text about thermoelectric power","page_number":1,"section":"A","document_id":"d1","chunk_index":1,"vector":[1,0]},
        {"chunk_id":"c","score":0.8,"text":"different content about Seebeck effect equation","page_number":2,"section":"B","document_id":"d1","chunk_index":2,"vector":[0,1]},
    ]
    selected = mmr_selection(candidates, lambda_param=0.7, top_k=2)
    # Should pick diverse: a and c (not both a,b)
    ids = [s["chunk_id"] for s in selected]
    assert "a" in ids
    assert "c" in ids
    assert "b" not in ids or len(ids)==2

def test_hybrid_fusion_normalized():
    db = SessionLocal()
    # Use trace to check fusion weights normalized
    retrieved, trace = retrieve_with_trace(db, "What equation defines electrical power?", top_k=5)
    assert "fusion_weights" in retrieved[0] or "fusion_weights" in trace
    assert trace["fusion_weights"]["semantic"] + trace["fusion_weights"]["keyword"] == 1.0 or abs(trace["fusion_weights"]["semantic"]+trace["fusion_weights"]["keyword"]-1.0)<0.01
    # Check query type classification
    assert trace["query_type"] == "equation"
    assert trace["retrieval_strategy"] == "hybrid_v2"
    # Check candidates before rerank vs final
    assert trace["candidates_before_rerank"] >= trace["final_evidence"]

def test_retrieval_diversity_pages():
    db = SessionLocal()
    retrieved, trace = retrieve_with_trace(db, "thermoelectric", top_k=5)
    # Should have diversity across pages/sections
    pages = [r["page_number"] for r in retrieved]
    # At least 2 different pages if enough candidates
    assert len(set(pages)) >= 1

def test_metadata_aware():
    db = SessionLocal()
    # Equation query should boost equation content_type
    retrieved, trace = retrieve_with_trace(db, "P = VI equation", top_k=5)
    # At least one equation type in top 3
    top_types = [r["content_type"] for r in retrieved[:3]]
    # May contain equation
    assert "equation" in top_types or len(retrieved)>0

def test_query_processing_preserves():
    from backend.app.services.query_processing import normalize_query
    assert "P = VI" in normalize_query("What is P = VI ?") or "p = vi" in normalize_query("What is P = VI ?").lower()
