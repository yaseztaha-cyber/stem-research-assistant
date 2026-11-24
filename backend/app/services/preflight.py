import sys
import pathlib
import importlib.metadata

def check_python():
    import platform
    v = platform.python_version()
    return True, f"Python {v}"

def check_dependencies():
    required = ["fastapi","sqlalchemy","pypdf","scikit-learn","numpy","pandas","sympy"]
    missing = []
    for pkg in required:
        try:
            importlib.metadata.version(pkg)
        except:
            try:
                __import__(pkg.replace("-","_"))
            except:
                missing.append(pkg)
    if missing:
        return False, f"Missing: {', '.join(missing)}"
    return True, "All core dependencies present"

def check_embedding_provider():
    from ..config import settings
    provider = settings.embedding_provider
    model = settings.dense_embedding_model
    # Try to load dense if requested
    if provider == "dense":
        try:
            from sentence_transformers import SentenceTransformer
            # Try to load model (may download)
            # We just check if we can import, not necessarily load (to avoid download in preflight)
            # Check if model files exist locally or can be loaded
            try:
                # Attempt to check model availability without download: try to list?
                # For now, try to actually load with local_files_only True to see if cached
                try:
                    m = SentenceTransformer(model, local_files_only=True)
                    return True, f"Dense model {model} available (cached)"
                except:
                    return False, f"Dense model {model} not cached, requires download (torch + sentence-transformers needed)"
            except Exception as e:
                return False, f"Dense model check failed: {e}"
        except ImportError as e:
            return False, f"sentence-transformers not installed: {e}"
    else:
        return True, f"Embedding provider {provider} (TF-IDF/OpenAI) available"

def check_reranker_provider():
    from ..config import settings
    provider = settings.reranker_provider
    model = settings.cross_encoder_model
    if provider == "cross_encoder":
        try:
            from sentence_transformers import CrossEncoder
            try:
                m = CrossEncoder(model, local_files_only=True)
                return True, f"CrossEncoder {model} available (cached)"
            except:
                return False, f"CrossEncoder {model} not cached, requires download"
        except ImportError as e:
            return False, f"sentence-transformers not installed for CrossEncoder: {e}"
    else:
        return True, f"Reranker {provider} available"

def check_database():
    from pathlib import Path
    from ..config import settings
    db_path = Path(settings.database_url.replace("sqlite:///", ""))
    if db_path.exists():
        return True, f"Database {db_path} exists"
    else:
        return False, f"Database {db_path} missing - run init_db"

def check_demo_documents():
    from pathlib import Path
    base = Path("demo_data")
    if not base.exists():
        return False, "demo_data missing"
    files = list(base.glob("*"))
    if len(files) < 3:
        return False, f"Only {len(files)} demo files, expected >=3"
    return True, f"Demo documents {len(files)} files"

def check_evaluation_dataset():
    try:
        from ..database import SessionLocal
        import backend.app.models.all_models
        from ..models.evaluation import EvaluationCase
        db = SessionLocal()
        count = db.query(EvaluationCase).count()
        db.close()
        if count >= 50:
            return True, f"Evaluation dataset {count} cases"
        else:
            return False, f"Evaluation dataset only {count} cases, expected ~100"
    except Exception as e:
        return False, f"Evaluation check failed: {e}"

def check_configuration():
    from ..config import settings
    return True, f"Config: embedding={settings.embedding_provider}, reranker={settings.reranker_provider}, semantic_weight={settings.semantic_weight}"

def run_preflight():
    checks = [
        ("Python", check_python),
        ("Dependencies", check_dependencies),
        ("Embedding provider", check_embedding_provider),
        ("Reranker provider", check_reranker_provider),
        ("Database", check_database),
        ("Demo documents", check_demo_documents),
        ("Evaluation dataset", check_evaluation_dataset),
        ("Configuration", check_configuration),
    ]
    results = []
    all_pass = True
    for name, fn in checks:
        try:
            passed, msg = fn()
        except Exception as e:
            passed, msg = False, str(e)
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}: {msg}")
        results.append((name, passed, msg))
        if not passed:
            all_pass = False
    if not all_pass:
        print("\nBenchmark cannot run with current configuration for strict mode. Fix failures or use fallback (non-strict) mode.")
    else:
        print("\nAll preflight checks passed - benchmark can run.")
    return all_pass, results

if __name__ == "__main__":
    passed, _ = run_preflight()
    sys.exit(0 if passed else 1)
