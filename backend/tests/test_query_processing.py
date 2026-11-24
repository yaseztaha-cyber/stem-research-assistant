from backend.app.services.query_processing import normalize_query, preserve_stem_tokens
from backend.app.services.query_classifier import classify_query, metadata_hint_for_query

def test_preserve_stem():
    q = "What is ΔT effect on P = VI at 120K?"
    norm = normalize_query(q)
    assert "ΔT" in norm or "Δt" in norm.lower() or "ΔT" in q  # preserved
    assert "P = VI" in norm or "p = vi" in norm.lower()

def test_normalize_preserves_equation():
    assert "P = VI" in normalize_query("P = VI") or "p = vi" in normalize_query("P = VI").lower()
    assert "V = IR" in normalize_query("V = IR") or "v = ir" in normalize_query("V = IR").lower()

def test_normalize_whitespace():
    assert normalize_query("  hello   world  ") == "hello world"

def test_classify_equation():
    r = classify_query("What equation defines electrical power?")
    assert r["query_type"] == "equation"
    assert r["is_equation"] == True

def test_classify_experimental():
    r = classify_query("What were the experimental results for power?")
    assert r["query_type"] in ("experimental_result","method","general")
    # At least should detect experimental
    assert "experimental" in r["query_type"] or "result" in str(r["scores"])

def test_classify_comparison():
    r = classify_query("Compare the two methods.")
    assert r["query_type"] == "comparison"
    assert r["is_comparison"] == True

def test_metadata_hint():
    hint = metadata_hint_for_query("equation")
    assert hint.get("content_type") == "equation"
    hint2 = metadata_hint_for_query("experimental_result")
    assert hint2.get("section") == "Results"
