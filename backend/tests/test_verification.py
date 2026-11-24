from backend.app.services.grounding import verify_numeric_claim, verify_equation_claim, verify_causal_claim, verify_citations_v2, classify_claim_type, detect_causal_claim

def test_numeric_verification_supported():
    retrieved = [{"text": "The electrical output increased by approximately 14% when ΔT increased", "document_name":"paper.pdf","page_number":4,"chunk_id":"a","retrieval_score":0.8}]
    res = verify_numeric_claim("Output increased by 14%.", retrieved)
    assert res["support_status"] in ("supported","partially_supported")
    assert res["support_score"] > 0.5

def test_numeric_verification_unsupported():
    retrieved = [{"text": "Power was 4.2W", "document_name":"paper.pdf","page_number":4,"chunk_id":"a","retrieval_score":0.8}]
    res = verify_numeric_claim("Output increased by 99%.", retrieved)
    assert res["support_status"] in ("unsupported","contradicted")

def test_numeric_percent_variants():
    retrieved = [{"text": "Increased by 14 percent", "document_name":"paper.pdf","page_number":1,"chunk_id":"a","retrieval_score":0.8}]
    res = verify_numeric_claim("14% increase", retrieved)
    assert res["support_status"] == "supported"

def test_equation_verification():
    retrieved = [{"text": "Power: P = V * I defines electrical power", "document_name":"paper.pdf","page_number":1,"chunk_id":"a","retrieval_score":0.8}]
    assert verify_equation_claim("P = VI", retrieved)["support_status"] == "supported"
    assert verify_equation_claim("V = IR", retrieved)["support_status"] == "unsupported"

def test_equation_variants():
    retrieved = [{"text": "Ohm's law: V = I * R", "document_name":"paper.pdf","page_number":1,"chunk_id":"a","retrieval_score":0.8}]
    assert verify_equation_claim("V = IR", retrieved)["support_status"] == "supported"
    # P=VI vs P=V*I lenient
    retrieved2 = [{"text": "P = V * I", "document_name":"paper.pdf","page_number":1,"chunk_id":"a","retrieval_score":0.8}]
    assert verify_equation_claim("P = VI", retrieved2)["support_status"] == "supported"

def test_causal_protection():
    retrieved = [{"text": "Temperature and output were positively correlated", "document_name":"paper.pdf","page_number":4,"chunk_id":"a","retrieval_score":0.8}]
    res = verify_causal_claim("Higher temperature causes increased output.", retrieved)
    assert res["support_status"] == "unsupported"
    assert "correlation" in res.get("reason","").lower() or "causation" in res.get("reason","").lower()

def test_causal_supported():
    retrieved = [{"text": "Higher temperature causes increased output due to Seebeck", "document_name":"paper.pdf","page_number":4,"chunk_id":"a","retrieval_score":0.8}]
    res = verify_causal_claim("Higher temperature causes increased output.", retrieved)
    assert res["support_status"] == "supported"

def test_citation_validation():
    retrieved = [
        {"document_name":"paper.pdf","page_number":7,"chunk_id":"abc-123","text":"output 14%","retrieval_score":0.8},
        {"document_name":"paper.pdf","page_number":2,"chunk_id":"def-456","text":"Seebeck","retrieval_score":0.7}
    ]
    ans = "The output increased by 14% [SOURCE: paper.pdf p.7] and Seebeck is defined [SOURCE: paper.pdf p.2]"
    res = verify_citations_v2(ans, retrieved)
    assert res["valid_count"] == 2
    assert res["citation_accuracy"] == 1.0
    # Broken citation
    ans2 = "Fake claim [SOURCE: missing.pdf p.99]"
    res2 = verify_citations_v2(ans2, retrieved)
    assert res2["valid_count"] == 0
    assert res2["invalid_count"] == 1

def test_claim_types():
    assert classify_claim_type("P = VI defines power") == "equation"
    assert classify_claim_type("The output increased by 14%") == "number"
    assert classify_claim_type("This causes increased efficiency") == "causal_claim"

def test_detect_causal():
    assert detect_causal_claim("Temperature causes output")["has_causal"] == True
    assert detect_causal_claim("Temperature correlates with output")["has_causal"] == False
