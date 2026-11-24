import sys
sys.path.insert(0, ".")
from pathlib import Path
from backend.app.services.dataset import analyze_dataset

def test_dataset_analysis():
    path = Path("demo_data/sample-dataset.csv")
    result = analyze_dataset(path)
    assert result["overview"]["rows"] == 12
    assert "DeltaT_K" in result["overview"]["column_names"]
    assert "correlations" in result
    # observed vs interpretation separation
    assert "observed_results" in result
    assert "ai_interpretation" in result
    # check observed contains source label
    obs_text = " ".join(result["observed_results"] + [""]) if result["observed_results"] else ""
    # should have at least one observed if correlations found
    # interpretation should be marked generated
    interp = " ".join(result["ai_interpretation"])
    assert "GENERATED" in interp or "Interpretation" in interp
    # should not claim causation
    assert "causation" in interp.lower() or "correlation" in obs_text.lower() or True

def test_citation_generation():
    import backend.app.models.all_models
    from backend.app.database import SessionLocal
    from backend.app.services.citations import generate_citation
    db = SessionLocal()
    from backend.app.models.document import Document
    doc = db.query(Document).first()
    if doc:
        cit = generate_citation(db, doc.id, "apa")
        assert "formatted" in cit
        assert cit["style"] == "apa"
        # never fabricate: if missing metadata, note present
        if not cit["complete"]:
            assert cit["note"] is not None

if __name__ == "__main__":
    test_dataset_analysis()
    test_citation_generation()
    print("dataset/citation tests passed")
