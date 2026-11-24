import sys
sys.path.insert(0, ".")
from backend.app.services.grounding import extract_claims, evaluate_grounding, verify_citations

def test_claim_classification():
    text = """The experiment increased electrical output by approximately 14%. [SOURCE: paper.pdf p.7]
This can be understood as the system converting a larger temperature gradient into a larger thermoelectric voltage. [GENERATED]
According to the uploaded paper, the Seebeck coefficient is 210 uV/K. [SOURCE]"""
    claims = extract_claims(text)
    # should distinguish at least 2 source, 1 generated
    types = [c["type"] for c in claims]
    assert "source" in types
    assert "generated" in types

def test_grounding_score():
    claims = [{"text": "The output increased by 14%.", "type": "source"}, {"text": "This suggests mechanism involves thermal gradient.", "type": "generated"}]
    retrieved = [
        {"text": "The electrical output increased by approximately 14% when DeltaT increased.", "retrieval_score": 0.85, "page_number":7, "document_name":"paper.pdf"},
        {"text": "Seebeck effect converts temperature gradients.", "retrieval_score": 0.6, "page_number":2, "document_name":"paper.pdf"},
    ]
    grounding = evaluate_grounding(claims, retrieved, "The output increased by 14% [SOURCE] This suggests mechanism [GENERATED]")
    assert 0 <= grounding["score"] <= 1
    assert grounding["percentage"] >= 0
    assert "retrieval_relevance" in grounding["factors"]

def test_citation_verification():
    answer = "The output increased by 14% [SOURCE: paper.pdf p.7] and voltage is V=IR [SOURCE]"
    retrieved = [{"document_name":"paper.pdf","page_number":7,"text":"output 14%"}]
    result = verify_citations(answer, retrieved)
    assert result["has_citations"] == True
    assert result["total_found"] >= 2

if __name__ == "__main__":
    test_claim_classification()
    test_grounding_score()
    test_citation_verification()
    print("grounding tests passed")
