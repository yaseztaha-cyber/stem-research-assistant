import sys
sys.path.insert(0, ".")
from backend.app.services.chunking import structure_aware_chunk, detect_content_type

def test_structure_aware_chunk():
    pages = [
        {"page_number": 1, "text": "Abstract\nThis paper investigates thermoelectric conversion.\n\nThe Seebeck effect converts temperature gradients.\n\nV = S * DeltaT"},
        {"page_number": 2, "text": "1. Introduction\nThermoelectric generators convert heat.\n\nKey equation: V = I * R\n\nPower follows P = V * I"}
    ]
    sections = [
        {"title": "Abstract", "heading_hierarchy": "Abstract", "section_type": "abstract", "text": "This paper investigates thermoelectric conversion. The Seebeck effect converts temperature gradients. V = S * DeltaT", "page_number":1, "order_index":0},
        {"title": "Introduction", "heading_hierarchy": "Introduction", "section_type": "introduction", "text": "Thermoelectric generators convert heat. Key equation: V = I * R Power follows P = V * I", "page_number":2, "order_index":1},
    ]
    chunks = structure_aware_chunk(pages, sections, max_tokens=30)
    assert len(chunks) >= 2
    # check structure preserved
    for c in chunks:
        assert "page_number" in c
        assert "section" in c
        assert "content_type" in c
        assert c["token_count"] > 0
    # equation boundary: should have separate equation chunk
    eq_chunks = [c for c in chunks if c["content_type"]=="equation"]
    assert len(eq_chunks) >= 1

def test_detect_content_type():
    assert detect_content_type("This is defined as a thermoelectric generator", "Introduction") == "definition"
    assert detect_content_type("V = I * R", "Equations") == "equation"
    assert detect_content_type("Experimental procedure step 1", "Procedure") == "procedure"

if __name__ == "__main__":
    test_structure_aware_chunk()
    test_detect_content_type()
    print("chunking tests passed")
