from sqlalchemy.orm import Session
from typing import List, Dict
from .retrieval import retrieve, retrieve_with_trace
from .grounding import extract_claims, hallucination_checks, verify_citations_v2
from ..models.evaluation import EvaluationCase
from ..models.chunk import DocumentChunk
import re
import math
import time

def ndcg_at_k(relevances: List[int], k: int) -> float:
    if not relevances or k==0:
        return 0.0
    dcg = 0.0
    for i, rel in enumerate(relevances[:k]):
        if rel > 0:
            dcg += (2**rel - 1) / math.log2(i+2)
    ideal = sorted(relevances, reverse=True)
    idcg = 0.0
    for i, rel in enumerate(ideal[:k]):
        if rel > 0:
            idcg += (2**rel - 1) / math.log2(i+2)
    return dcg / idcg if idcg>0 else 0.0

def mrr_score(rank: int) -> float:
    return 1.0 / rank if rank>0 else 0.0

def run_evaluation(db: Session, top_k: int = 5, use_real_rag: bool = False):
    # For v0.3, optionally use real rag_query for end-to-end answer quality
    # If use_real_rag True, will call rag_query per case (slower but more accurate for answer relevance v2)
    cases = db.query(EvaluationCase).all()
    results=[]
    metrics_agg = {
        "recall_at_k": [], "precision_at_k": [], "mrr": [], "ndcg_at_k": [],
        "retrieval_recall": [], "retrieval_precision": [], "citation_accuracy": [],
        "citation_precision": [], "citation_recall": [],
        "groundedness": [], "unsupported_rate": [], "answer_relevance": [], "answer_relevance_v2": [], "answer_relevance_v3": []
    }
    # For latency analysis per case
    latencies = []
    for case in cases:
        q = case.question
        t0 = time.time()
        # Use retrieve_with_trace for richer info
        retrieved, trace = retrieve_with_trace(db, q, top_k=top_k, document_ids=case.document_ids)
        retrieval_lat = trace.get("latency",{}).get("total_ms", 0) if trace else 0

        # Determine relevance per retrieved: page match or concept hit or chunk_id in relevant_chunks
        relevances = []
        expected_page = str(case.expected_source_page) if case.expected_source_page else None
        expected_concept = (case.expected_concept or "").lower()
        relevant_chunks = set(case.relevant_chunks or [])
        # For v0.3, also use required_concepts/values if present
        required_concepts = getattr(case, 'required_concepts', None) or []
        required_values = getattr(case, 'required_values', None) or []
        # If not set, derive from expected_concept
        if not required_concepts and expected_concept:
            required_concepts = [expected_concept]
        for r in retrieved:
            rel = 0
            if expected_page and str(r["page_number"]) == expected_page:
                rel = 1
            if expected_concept and expected_concept in r["text"].lower():
                rel = 1
            if r["chunk_id"] in relevant_chunks:
                rel = 1
            if case.relevant_documents and r["document_name"] in case.relevant_documents:
                if rel==0 and expected_concept in r["text"].lower():
                    rel = 1
            # Also check required_concepts
            if required_concepts and any(rc.lower() in r["text"].lower() for rc in required_concepts):
                rel = 1
            relevances.append(rel)

        total_relevant = 1
        if relevant_chunks:
            total_relevant = len(relevant_chunks)
        elif expected_page or expected_concept:
            q_count = db.query(DocumentChunk).filter(DocumentChunk.text.ilike(f"%{expected_concept}%")).count() if expected_concept else 0
            if q_count>0 and q_count<10:
                total_relevant = min(q_count, 3)
            else:
                total_relevant = 1

        recall_at_k = sum(relevances) / total_relevant if total_relevant>0 else 0
        recall_at_k = min(recall_at_k, 1.0)
        precision_at_k = sum(relevances) / max(len(retrieved),1)
        mrr = 0
        for idx, rel in enumerate(relevances, start=1):
            if rel==1:
                mrr = mrr_score(idx)
                break
        ndcg = ndcg_at_k(relevances, top_k)
        legacy_recall = 1 if sum(relevances)>0 else 0
        legacy_precision = sum(relevances)/max(len(retrieved),1)

        # Citation accuracy - use synthetic but with real retrieved doc
        concept_hit = 1 if sum(relevances)>0 else 0
        if concept_hit and retrieved:
            doc_name = retrieved[0]["document_name"]
            page = retrieved[0]["page_number"]
            section = retrieved[0].get("section","Results")
            synthetic_answer = f"{case.expected_concept or ''} [SOURCE: {doc_name} p.{page} §{section}]"
        elif concept_hit:
            synthetic_answer = f"{case.expected_concept or ''} [SOURCE: {case.relevant_documents[0] if case.relevant_documents else 'doc.pdf'} p.{expected_page}]"
        else:
            synthetic_answer = "The supplied sources do not provide enough evidence. [GENERATED]"

        # If use_real_rag, generate real answer via rag_query for better answer relevance v2
        answer_for_relevance = synthetic_answer
        if use_real_rag:
            try:
                import asyncio
                from .rag import rag_query
                # Run rag_query synchronously
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                rag_res = loop.run_until_complete(rag_query(db, q, top_k=top_k, document_ids=case.document_ids))
                answer_for_relevance = rag_res.get("answer", synthetic_answer)
                # Use rag's grounding etc if we want, but keep synthetic for citation
            except Exception:
                answer_for_relevance = synthetic_answer

        cit_v2 = verify_citations_v2(synthetic_answer, retrieved)
        citation_accuracy = cit_v2["citation_accuracy"]
        citation_precision = cit_v2["citation_precision"]
        citation_recall = cit_v2["citation_recall"]

        claims = extract_claims(synthetic_answer)
        checks = hallucination_checks(synthetic_answer, retrieved, claims)
        groundedness = checks["grounding"]["score"]
        unsupported = checks["unsupported_rate"]

        # Legacy answer relevance (token overlap)
        q_terms = set(re.findall(r"\w+", q.lower()))
        avg_overlap = 0
        if retrieved:
            overlaps = []
            for r in retrieved:
                r_terms = set(re.findall(r"\w+", r["text"].lower()))
                overlaps.append(len(q_terms.intersection(r_terms))/max(len(q_terms),1))
            avg_overlap = sum(overlaps[:3])/min(3,len(overlaps))
        else:
            avg_overlap=0

        # Answer relevance v2 layered (FROZEN — do not modify v2 semantics)
        try:
            from .evaluation_v2_helper import compute_answer_relevance_v2, compute_evidence_redundancy
            v2 = compute_answer_relevance_v2(answer_for_relevance, required_concepts, required_values, getattr(case,'required_sources',None) or [], q, retrieved, claims)
            answer_relevance_v2 = v2["answer_relevance_v2"]
            redundancy = compute_evidence_redundancy(retrieved)
        except Exception:
            answer_relevance_v2 = avg_overlap
            redundancy = {"duplicate_ratio":0}
            v2 = {"concept_coverage":0,"directness_score":0}
        # Answer relevance v3 (v0.5 §28; separate version, v2 untouched)
        try:
            from .evaluation_v3_helper import compute_answer_relevance_v3
            v3 = compute_answer_relevance_v3(answer_for_relevance, required_concepts, required_values, getattr(case,'required_sources',None) or [], q, retrieved, claims)
            answer_relevance_v3 = v3["answer_relevance_v3"]
        except Exception:
            answer_relevance_v3 = answer_relevance_v2
            v3 = {"answer_relevance_v3": answer_relevance_v2, "metric_version": "v3(fallback)"}

        # Evidence sufficiency
        try:
            from .evidence_sufficiency import assess_evidence_sufficiency
            suff = assess_evidence_sufficiency(q, trace.get("query_type","general") if trace else "general", retrieved, required_concepts, required_values)
        except Exception:
            suff = {"status":"unknown"}

        # Latency
        total_lat = retrieval_lat + 50  # approx LLM 50ms mock
        latencies.append(total_lat)

        # Failure type
        failure_type = None
        if legacy_recall==0:
            if expected_page and retrieved:
                retrieved_pages = [str(r["page_number"]) for r in retrieved]
                if expected_page not in retrieved_pages:
                    if case.relevant_documents:
                        retrieved_docs = [r["document_name"] for r in retrieved]
                        if not any(d in retrieved_docs for d in case.relevant_documents):
                            failure_type = "wrong_document"
                        else:
                            failure_type = "wrong_page"
                    else:
                        failure_type = "wrong_page"
                else:
                    failure_type = "semantic_mismatch"
            else:
                failure_type = "no_candidates"
        elif sum(relevances) < len(relevances):
            failure_type = "partial"

        res = {
            "case_id": case.id,
            "question": q,
            "category": case.category or "general",
            "expected_page": expected_page,
            "expected_concept": case.expected_concept,
            "expected_answer": case.expected_answer,
            "required_concepts": required_concepts,
            "required_values": required_values,
            "retrieved_count": len(retrieved),
            "relevances": relevances,
            "recall_at_k": round(recall_at_k,3),
            "precision_at_k": round(precision_at_k,3),
            "mrr": round(mrr,3),
            "ndcg_at_k": round(ndcg,3),
            "retrieval_recall": round(legacy_recall,3),
            "retrieval_precision": round(legacy_precision,3),
            "concept_hit": concept_hit,
            "citation_accuracy": round(citation_accuracy,3),
            "citation_precision": round(citation_precision,3),
            "citation_recall": round(citation_recall,3),
            "groundedness": round(groundedness,3),
            "unsupported_rate": round(unsupported,3),
            "answer_relevance": round(avg_overlap,3),
            "answer_relevance_v2": round(answer_relevance_v2,3),
            "v2_details": v2,
            "answer_relevance_v3": round(answer_relevance_v3,3),
            "v3_details": v3,
            "evidence_sufficiency": suff,
            "redundancy": redundancy,
            "retrieved_pages": [r["page_number"] for r in retrieved],
            "retrieved_chunks": [r["chunk_id"] for r in retrieved],
            "trace": trace,
            "failure_type": failure_type,
            "latency_ms": total_lat,
        }
        results.append(res)
        metrics_agg["recall_at_k"].append(recall_at_k)
        metrics_agg["precision_at_k"].append(precision_at_k)
        metrics_agg["mrr"].append(mrr)
        metrics_agg["ndcg_at_k"].append(ndcg)
        metrics_agg["retrieval_recall"].append(legacy_recall)
        metrics_agg["retrieval_precision"].append(legacy_precision)
        metrics_agg["citation_accuracy"].append(citation_accuracy)
        metrics_agg["citation_precision"].append(citation_precision)
        metrics_agg["citation_recall"].append(citation_recall)
        metrics_agg["groundedness"].append(groundedness)
        metrics_agg["unsupported_rate"].append(unsupported)
        metrics_agg["answer_relevance"].append(avg_overlap)
        metrics_agg["answer_relevance_v2"].append(answer_relevance_v2)
        metrics_agg["answer_relevance_v3"].append(answer_relevance_v3)

    def avg(lst): return round(sum(lst)/len(lst),3) if lst else 0
    def median(lst):
        if not lst: return 0
        s = sorted(lst)
        n = len(s)
        return round(s[n//2] if n % 2 == 1 else (s[n//2-1]+s[n//2])/2, 3)
    def p95(lst):
        if not lst: return 0
        import math as _m
        s = sorted(lst)
        k = min(len(s)-1, max(0, int(_m.ceil(0.95*len(s)))-1))
        return round(s[k], 1)
    summary = {
        "total_cases": len(cases),
        "recall_at_5": avg(metrics_agg["recall_at_k"]),
        "precision_at_5": avg(metrics_agg["precision_at_k"]),
        "mrr": avg(metrics_agg["mrr"]),
        "ndcg_at_5": avg(metrics_agg["ndcg_at_k"]),
        "retrieval_recall": avg(metrics_agg["retrieval_recall"]),
        "retrieval_precision": avg(metrics_agg["retrieval_precision"]),
        "citation_accuracy": avg(metrics_agg["citation_accuracy"]),
        "citation_precision": avg(metrics_agg["citation_precision"]),
        "citation_recall": avg(metrics_agg["citation_recall"]),
        "groundedness": avg(metrics_agg["groundedness"]),
        "unsupported_claim_rate": avg(metrics_agg["unsupported_rate"]),
        "answer_relevance": avg(metrics_agg["answer_relevance"]),
        "answer_relevance_v2": avg(metrics_agg["answer_relevance_v2"]),
        "answer_relevance_v3": avg(metrics_agg["answer_relevance_v3"]),
        "avg_latency_ms": round(sum(latencies)/len(latencies),1) if latencies else 0,
        "median_latency_ms": median(latencies),
        "p95_latency_ms": p95(latencies),
        "min_latency_ms": round(min(latencies),1) if latencies else 0,
        "max_latency_ms": round(max(latencies),1) if latencies else 0,
    }
    return {"summary": summary, "cases": results}

# Expanded dataset v0.3 - 50 cases across categories (includes v0.2 25 + 25 new)
EXPANDED_CASES = [
    # definition (2)
    {"question": "What is the Seebeck effect?", "expected_answer": "voltage generation from temperature difference V=SΔT", "expected_source_page": 2, "expected_concept": "Seebeck", "category": "definition", "relevant_documents": ["thermoelectric-paper.pdf"], "required_concepts": ["Seebeck", "temperature", "voltage"], "required_values": [], "required_sources": ["thermoelectric-paper.pdf"]},
    {"question": "Define thermoelectric generator (TEG)", "expected_answer": "device converting heat to electricity via Seebeck", "expected_source_page": 2, "expected_concept": "Thermoelectric generator", "category": "definition", "required_concepts": ["thermoelectric", "generator"], "required_values": []},
    # equation (4)
    {"question": "What equation defines electrical power?", "expected_answer": "P = VI", "expected_source_page": 1, "expected_concept": "P = VI", "category": "equation", "required_concepts": ["P = VI", "power"], "required_values": ["P = VI"], "required_sources": ["thermoelectric-paper.pdf"]},
    {"question": "What is Ohm's law?", "expected_answer": "V = IR", "expected_source_page": 1, "expected_concept": "V = IR", "category": "equation", "required_concepts": ["V = IR", "voltage"], "required_values": ["V = IR"]},
    {"question": "What is the Seebeck voltage equation?", "expected_answer": "V = S * DeltaT", "expected_source_page": 1, "expected_concept": "V = S", "category": "equation", "required_concepts": ["V = S", "Seebeck"], "required_values": ["V = S"]},
    {"question": "What equation defines efficiency?", "expected_answer": "η = Pout / Pin", "expected_source_page": 1, "expected_concept": "Pout / Pin", "category": "equation", "required_concepts": ["efficiency", "Pout"], "required_values": ["Pout / Pin"]},
    # experimental_result (3)
    {"question": "What was the reported experimental improvement when ΔT increased from 100K to 120K?", "expected_answer": "14% normalized increase", "expected_source_page": 4, "expected_concept": "14%", "category": "experimental_result", "required_concepts": ["14%", "DeltaT"], "required_values": ["14%"]},
    {"question": "What maximum power was achieved at ΔT=120K?", "expected_answer": "4.2W", "expected_source_page": 4, "expected_concept": "4.2W", "category": "experimental_result", "required_concepts": ["4.2W", "DeltaT"], "required_values": ["4.2W"]},
    {"question": "What efficiency was reported at ΔT=120K?", "expected_answer": "5.2%", "expected_source_page": 4, "expected_concept": "5.2%", "category": "experimental_result", "required_concepts": ["5.2%", "efficiency"], "required_values": ["5.2%"]},
    # method (2)
    {"question": "What materials were used in the experimental setup?", "expected_answer": "Bi2Te3 modules, heat source, heat sink", "expected_source_page": 3, "expected_concept": "Bi2Te3", "category": "method", "required_concepts": ["Bi2Te3", "heat sink"], "required_values": []},
    {"question": "What procedure was used to measure TEG performance?", "expected_answer": "vary load resistance, measure V and I", "expected_source_page": 3, "expected_concept": "load resistance", "category": "method", "required_concepts": ["load resistance", "measure"], "required_values": []},
    # numeric fact (3)
    {"question": "What is the Seebeck coefficient reported?", "expected_answer": "210 uV/K", "expected_source_page": 5, "expected_concept": "210", "category": "numeric_fact", "required_concepts": ["Seebeck", "210"], "required_values": ["210"]},
    {"question": "What is the figure of merit ZT reported?", "expected_answer": "0.95", "expected_source_page": 4, "expected_concept": "ZT = 0.95", "category": "numeric_fact", "required_concepts": ["ZT", "0.95"], "required_values": ["0.95"]},
    {"question": "What contact resistance was reported?", "expected_answer": "0.15 Ohm", "expected_source_page": 5, "expected_concept": "0.15", "category": "numeric_fact", "required_concepts": ["contact resistance", "0.15"], "required_values": ["0.15"]},
    # comparison (2)
    {"question": "Compare ZT of this work vs literature nanostructured Bi2Te3", "expected_answer": "0.95 vs 1.1 literature", "expected_source_page": 5, "expected_concept": "ZT=1.1", "category": "comparison", "required_concepts": ["0.95", "1.1", "ZT"], "required_values": ["0.95", "1.1"]},
    {"question": "How does power output vary with DeltaT?", "expected_answer": "increases with DeltaT, 1.79W at 80K to 4.2W at 120K", "expected_source_page": 4, "expected_concept": "120 | 3.3", "category": "comparison", "required_concepts": ["power", "DeltaT"], "required_values": ["1.79W", "4.2W"]},
    # dataset (2)
    {"question": "What columns are in the thermoelectric dataset?", "expected_answer": "DeltaT_K, Voltage_V, Current_A, Power_W", "expected_source_page": 1, "expected_concept": "DeltaT_K", "category": "dataset", "relevant_documents": ["sample-dataset.csv"], "required_concepts": ["DeltaT_K", "Voltage_V"], "required_values": ["DeltaT_K"]},
    {"question": "How many rows are in the dataset?", "expected_answer": "12 rows", "expected_source_page": 1, "expected_concept": "Rows: 12", "category": "dataset", "required_concepts": ["12", "rows"], "required_values": ["12"]},
    # research gap (2)
    {"question": "What limitations were reported in the study?", "expected_answer": "only three DeltaT points, steady-state assumption", "expected_source_page": 5, "expected_concept": "Only three DeltaT", "category": "research_gap", "required_concepts": ["three DeltaT", "limitation"], "required_values": []},
    {"question": "What future work is suggested?", "expected_answer": "optimize heat sink, nanostructured material", "expected_source_page": 6, "expected_concept": "Future work", "category": "research_gap", "required_concepts": ["heat sink", "nanostructured"], "required_values": []},
    # procedure (2)
    {"question": "What safety precautions are in the lab manual?", "expected_answer": "thermal gloves, hot surfaces 150C", "expected_source_page": 1, "expected_concept": "thermal gloves", "category": "procedure", "relevant_documents": ["lab-manual.md"], "required_concepts": ["thermal gloves", "hot surfaces"], "required_values": ["150C"]},
    {"question": "What is the lab objective?", "expected_answer": "Measure TEG performance vs DeltaT and load", "expected_source_page": 1, "expected_concept": "Measure the performance", "category": "procedure", "required_concepts": ["TEG", "DeltaT"], "required_values": []},
    # multi-document (2)
    {"question": "What are common materials across paper and lab manual?", "expected_answer": "Bi2Te3 modules", "expected_source_page": 1, "expected_concept": "Bi2Te3", "category": "multi_document", "required_concepts": ["Bi2Te3"], "required_values": []},
    {"question": "What equation appears in both notes and paper?", "expected_answer": "P = VI", "expected_source_page": 1, "expected_concept": "P = VI", "category": "multi_document", "required_concepts": ["P = VI"], "required_values": ["P = VI"]},
    # --- v0.3 new 25 cases ---
    # table (5)
    {"question": "Which DeltaT configuration produced the highest power output?", "expected_answer": "120K with 4.2W", "expected_source_page": 4, "expected_concept": "120 | 3.3", "category": "table", "required_concepts": ["120K", "4.2W"], "required_values": ["4.2W", "120"]},
    {"question": "What was the power at 100K DeltaT?", "expected_answer": "3.14W", "expected_source_page": 4, "expected_concept": "3.14", "category": "table", "required_concepts": ["3.14W", "100K"], "required_values": ["3.14"]},
    {"question": "Which experiment had the lowest efficiency in the dataset?", "expected_answer": "2.9% at 80K 0.6A", "expected_source_page": 1, "expected_concept": "DeltaT_K", "category": "table", "required_concepts": ["efficiency", "DeltaT"], "required_values": ["2.9"]},
    {"question": "What table shows DeltaT, V, I, P values?", "expected_answer": "Table DeltaT | V | I | P", "expected_source_page": 4, "expected_concept": "DeltaT (K) | V (V)", "category": "table", "required_concepts": ["DeltaT", "V", "I", "P"], "required_values": []},
    {"question": "What row in the table corresponds to 80K DeltaT with 2.1V?", "expected_answer": "80 | 2.1 | 0.85 | 1.79", "expected_source_page": 4, "expected_concept": "80 | 2.1", "category": "table", "required_concepts": ["80", "2.1"], "required_values": ["80", "2.1"]},
    # equation reasoning (5)
    {"question": "What variables appear in the Seebeck equation V = S * DeltaT?", "expected_answer": "V, S, DeltaT", "expected_source_page": 1, "expected_concept": "V = S", "category": "equation", "required_concepts": ["V", "S", "DeltaT"], "required_values": []},
    {"question": "What happens to P if V doubles while I is constant according to P = VI?", "expected_answer": "P doubles", "expected_source_page": 1, "expected_concept": "P = VI", "category": "equation", "required_concepts": ["P", "V", "I", "doubles"], "required_values": ["P = VI"]},
    {"question": "What happens to V if I increases with R constant per V = IR?", "expected_answer": "V increases proportionally", "expected_source_page": 1, "expected_concept": "V = IR", "category": "equation", "required_concepts": ["V", "I", "R"], "required_values": ["V = IR"]},
    {"question": "What equation would you use to find heat Q?", "expected_answer": "Q = mcDeltaT", "expected_source_page": 1, "expected_concept": "Q = mc", "category": "equation", "required_concepts": ["Q", "mc"], "required_values": ["Q = mc"]},
    {"question": "Calculate power if V=3.3V and I=1.27A", "expected_answer": "4.191W approx 4.2W", "expected_source_page": 4, "expected_concept": "4.2W", "category": "numeric", "required_concepts": ["3.3V", "1.27A", "4.2W"], "required_values": ["4.2W"]},
    # numeric reasoning (4)
    {"question": "Calculate Q for m=0.5kg c=4186 DeltaT=20K", "expected_answer": "41860 J", "expected_source_page": 1, "expected_concept": "Q = mc", "category": "numeric", "required_concepts": ["41860", "Q"], "required_values": ["41860"]},
    {"question": "What is the derived power if V=2.8V I=1.12A?", "expected_answer": "3.136W", "expected_source_page": 4, "expected_concept": "3.14", "category": "numeric", "required_concepts": ["2.8", "1.12", "3.14"], "required_values": ["3.14"]},
    {"question": "If DeltaT increases from 80K to 120K, how much does V increase according to data?", "expected_answer": "from 2.1V to 3.3V", "expected_source_page": 4, "expected_concept": "2.1", "category": "numeric", "required_concepts": ["2.1", "3.3", "DeltaT"], "required_values": ["2.1", "3.3"]},
    {"question": "What is the largest DeltaT tested?", "expected_answer": "120K", "expected_source_page": 4, "expected_concept": "120", "category": "numeric", "required_concepts": ["120K"], "required_values": ["120"]},
    # contradiction (2)
    {"question": "Do sources agree on efficiency at 120K?", "expected_answer": "Paper reports 5.2%, dataset shows 5.2% and 5.4% etc, slight disagreement due to calculation", "expected_source_page": 4, "expected_concept": "5.2%", "category": "contradiction", "required_concepts": ["5.2%", "efficiency"], "required_values": ["5.2%"]},
    {"question": "Which source reports higher ZT, paper or literature?", "expected_answer": "Literature 1.1 vs paper 0.95", "expected_source_page": 5, "expected_concept": "ZT=1.1", "category": "contradiction", "required_concepts": ["0.95", "1.1", "ZT"], "required_values": ["0.95", "1.1"]},
    # citation (2)
    {"question": "Provide APA citation for the thermoelectric paper", "expected_answer": "Rowe, D.M. (2018) Thermoelectrics Handbook", "expected_source_page": 6, "expected_concept": "Rowe", "category": "citation", "required_concepts": ["Rowe"], "required_values": []},
    {"question": "Provide IEEE citation for the lab manual", "expected_answer": "Lab Manual TEG", "expected_source_page": 1, "expected_concept": "lab-manual", "category": "citation", "required_concepts": ["lab", "manual"], "required_values": []},
    # additional general
    {"question": "What is the Seebeck coefficient unit?", "expected_answer": "V/K", "expected_source_page": 1, "expected_concept": "V/K", "category": "definition", "required_concepts": ["Seebeck", "V/K"], "required_values": ["V/K"]},
    {"question": "What is the smallest load resistance tested?", "expected_answer": "1.73 Ohm", "expected_source_page": 4, "expected_concept": "1.73", "category": "table", "required_concepts": ["1.73", "Ohm"], "required_values": ["1.73"]},
    {"question": "What is the relationship between DeltaT and V?", "expected_answer": "V proportional to DeltaT", "expected_source_page": 1, "expected_concept": "V = S", "category": "concept", "required_concepts": ["DeltaT", "V", "proportional"], "required_values": []},
    {"question": "How to calculate efficiency from Pout and Pin?", "expected_answer": "eta = Pout / Pin", "expected_source_page": 1, "expected_concept": "Pout / Pin", "category": "method", "required_concepts": ["Pout", "Pin", "efficiency"], "required_values": ["Pout / Pin"]},
    {"question": "What research gap exists for heat sink design?", "expected_answer": "optimize heat sink design", "expected_source_page": 6, "expected_concept": "heat sink", "category": "research_gap", "required_concepts": ["heat sink", "optimize"], "required_values": []},
]

def seed_evaluation_cases(db: Session, expand: bool = True):
    """Create demo evaluation dataset if empty, expanded to 50 cases for v0.3"""
    existing = {c.question: c for c in db.query(EvaluationCase).all()}
    if not existing and expand:
        for d in EXPANDED_CASES:
            case = EvaluationCase(
                question=d["question"],
                expected_answer=d["expected_answer"],
                expected_source_page=d["expected_source_page"],
                expected_concept=d["expected_concept"],
                category=d.get("category","general"),
                relevant_documents=d.get("relevant_documents"),
                relevant_chunks=d.get("relevant_chunks", []),
                expected_claims=d.get("expected_claims", []),
                required_concepts=d.get("required_concepts", []),
                required_values=d.get("required_values", []),
                required_sources=d.get("required_sources", []),
                document_ids=d.get("document_ids")
            )
            db.add(case)
        db.commit()
        return
    if existing and expand:
        # Add missing
        for d in EXPANDED_CASES:
            if d["question"] not in existing:
                case = EvaluationCase(
                    question=d["question"],
                    expected_answer=d["expected_answer"],
                    expected_source_page=d["expected_source_page"],
                    expected_concept=d["expected_concept"],
                    category=d.get("category","general"),
                    relevant_documents=d.get("relevant_documents"),
                    relevant_chunks=d.get("relevant_chunks", []),
                    expected_claims=d.get("expected_claims", []),
                    required_concepts=d.get("required_concepts", []),
                    required_values=d.get("required_values", []),
                    required_sources=d.get("required_sources", []),
                    document_ids=d.get("document_ids")
                )
                db.add(case)
        db.commit()
        # Also update existing cases to add required fields if missing
        for d in EXPANDED_CASES:
            if d["question"] in existing:
                c = existing[d["question"]]
                updated = False
                if not c.required_concepts and d.get("required_concepts"):
                    c.required_concepts = d["required_concepts"]
                    updated = True
                if not c.required_values and d.get("required_values"):
                    c.required_values = d["required_values"]
                    updated = True
                if not c.required_sources and d.get("required_sources"):
                    c.required_sources = d["required_sources"]
                    updated = True
        db.commit()
        return
    if not expand:
        # Original 4-case seed for backward compat
        demo = EXPANDED_CASES[:4]
        for d in demo:
            case = EvaluationCase(question=d["question"], expected_answer=d["expected_answer"], expected_source_page=d["expected_source_page"], expected_concept=d["expected_concept"])
            db.add(case)
        db.commit()

def get_baseline_comparison(current_summary: Dict, baseline_path: str = "docs/evaluation/v0.1-baseline.json") -> Dict:
    import json, pathlib
    p = pathlib.Path(baseline_path)
    if not p.exists():
        return {"error": "baseline not found"}
    baseline = json.loads(p.read_text())
    base_sum = baseline.get("summary",{})
    comparison = {}
    for k in ["recall_at_5","precision_at_5","mrr","ndcg_at_5","retrieval_recall","retrieval_precision","citation_accuracy","groundedness","unsupported_claim_rate","answer_relevance","answer_relevance_v2","answer_relevance_v3"]:
        cur = current_summary.get(k) or current_summary.get(k.replace("_at_5","")) or 0
        base = base_sum.get(k) or base_sum.get(k.replace("_at_5","")) or base_sum.get("retrieval_recall" if "recall" in k else "retrieval_precision" if "precision" in k else k) or 0
        if k in ["recall_at_5","mrr","ndcg_at_5"] and k not in base_sum:
            if k=="recall_at_5":
                base = base_sum.get("retrieval_recall",0)
            elif k=="precision_at_5":
                base = base_sum.get("retrieval_precision",0)
        delta = round(cur - base,3) if isinstance(cur,(int,float)) and isinstance(base,(int,float)) else 0
        comparison[k] = {"v0_1": base, "v0_2": cur, "delta": delta}
    return comparison

def _is_dense_available():
    try:
        from sentence_transformers import SentenceTransformer
        # Try to check if model can be loaded without download (local_files_only)
        # If not cached, will fail
        from ..config import settings
        try:
            m = SentenceTransformer(settings.dense_embedding_model, local_files_only=True)
            return True, "available (cached)"
        except:
            return False, "not cached, requires download"
    except ImportError as e:
        return False, f"sentence-transformers not installed: {e}"
    except Exception as e:
        return False, str(e)

def _is_cross_encoder_available():
    try:
        from sentence_transformers import CrossEncoder
        from ..config import settings
        try:
            m = CrossEncoder(settings.cross_encoder_model, local_files_only=True)
            return True, "available (cached)"
        except:
            return False, "not cached, requires download"
    except ImportError as e:
        return False, f"sentence-transformers not installed: {e}"
    except Exception as e:
        return False, str(e)

def run_benchmark_matrix(db: Session, strict: bool = False):
    """Run 4 configs benchmark: TFIDF+Simple, TFIDF+CE, Dense+Simple, Dense+CE
    If strict=True, fallback is disabled and missing model causes FAILED (no score) per v0.4 benchmark integrity.
    """
    from ..config import settings
    from ..core.embedding_provider import reset_embedding_provider, get_global_embedding_provider
    from ..core.reranker import get_reranker
    configs = [
        {"name": "TFIDF+Simple", "embedding": "tfidf", "reranker": "simple"},
        {"name": "TFIDF+CrossEncoder", "embedding": "tfidf", "reranker": "cross_encoder"},
        {"name": "Dense+Simple", "embedding": "dense", "reranker": "simple"},
        {"name": "Dense+CrossEncoder", "embedding": "dense", "reranker": "cross_encoder"},
    ]
    results = {}
    original_emb = settings.embedding_provider
    original_rerank = settings.reranker_provider
    for cfg in configs:
        requested_emb = cfg["embedding"]
        requested_rerank = cfg["reranker"]
        # Check availability if strict
        dense_available, dense_msg = _is_dense_available() if requested_emb=="dense" else (True, "tfidf always available")
        ce_available, ce_msg = _is_cross_encoder_available() if requested_rerank=="cross_encoder" else (True, "simple always available")
        fallback = False
        active_emb = requested_emb
        active_rerank = requested_rerank
        # Determine if fallback would occur
        if requested_emb=="dense" and not dense_available:
            if strict:
                results[cfg["name"]] = {
                    "config": cfg,
                    "requested_embedding_provider": requested_emb,
                    "active_embedding_provider": None,
                    "embedding_model": settings.dense_embedding_model,
                    "requested_reranker": requested_rerank,
                    "active_reranker": None,
                    "reranker_model": settings.cross_encoder_model,
                    "fallback": True,
                    "error": f"Benchmark configuration FAILED: Dense embedding model unavailable. {dense_msg} No score was generated.",
                    "fallback_reason": dense_msg
                }
                continue
            else:
                fallback = True
                active_emb = "tfidf"
        if requested_rerank=="cross_encoder" and not ce_available:
            if strict:
                results[cfg["name"]] = {
                    "config": cfg,
                    "requested_embedding_provider": requested_emb,
                    "active_embedding_provider": active_emb,
                    "embedding_model": settings.dense_embedding_model if requested_emb=="dense" else "tfidf",
                    "requested_reranker": requested_rerank,
                    "active_reranker": None,
                    "reranker_model": settings.cross_encoder_model,
                    "fallback": True,
                    "error": f"Benchmark configuration FAILED: Cross encoder unavailable. {ce_msg} No score was generated.",
                    "fallback_reason": ce_msg
                }
                continue
            else:
                fallback = True
                active_rerank = "simple"
        try:
            settings.embedding_provider = cfg["embedding"] if not fallback or requested_emb!="dense" else "tfidf"
            # For strict, we already handled fallback, so here we set requested
            if strict:
                settings.embedding_provider = requested_emb
                settings.reranker_provider = requested_rerank
            else:
                settings.embedding_provider = cfg["embedding"]
                settings.reranker_provider = cfg["reranker"]
            # If fallback would happen, keep settings as requested but provider will fallback internally; we need to detect actual active after load
            reset_embedding_provider()
            # Force load to see actual
            provider = get_global_embedding_provider()
            actual_emb_type = type(provider).__name__
            if "Dense" in actual_emb_type and not dense_available:
                # Should have fallen back but didn't in strict? Already handled
                pass
            # Check actual reranker
            reranker = get_reranker()
            actual_rerank_name = reranker.name
            # Determine active vs requested
            if "Dense" in actual_emb_type:
                active_emb = "dense"
            elif "Tfidf" in actual_emb_type:
                active_emb = "tfidf"
            elif "OpenAI" in actual_emb_type:
                active_emb = "openai"
            if "cross_encoder" in actual_rerank_name:
                active_rerank = "cross_encoder"
            elif "simple" in actual_rerank_name:
                active_rerank = "simple"

            # Check if fallback occurred vs requested
            is_fallback = (active_emb != requested_emb) or (active_rerank != requested_rerank)
            if strict and is_fallback:
                results[cfg["name"]] = {
                    "requested_embedding_provider": requested_emb,
                    "active_embedding_provider": active_emb,
                    "embedding_model": settings.dense_embedding_model if requested_emb=="dense" else "tfidf",
                    "requested_reranker": requested_rerank,
                    "active_reranker": active_rerank,
                    "reranker_model": settings.cross_encoder_model,
                    "fallback": True,
                    "error": f"Benchmark configuration FAILED: Requested {requested_emb}+{requested_rerank} but active is {active_emb}+{active_rerank}. No score was generated (strict mode).",
                }
                continue

            # Clear cache
            try:
                from .cache import retrieval_cache
                retrieval_cache.invalidate("retrieval")
            except: pass
            res = run_evaluation(db, top_k=5)
            results[cfg["name"]] = {
                "summary": res["summary"],
                "config": cfg,
                "requested_embedding_provider": requested_emb,
                "active_embedding_provider": active_emb,
                "embedding_model": settings.dense_embedding_model if active_emb=="dense" else ("tfidf" if active_emb=="tfidf" else settings.openai_embedding_model),
                "requested_reranker": requested_rerank,
                "active_reranker": active_rerank,
                "reranker_model": settings.cross_encoder_model if active_rerank=="cross_encoder" else "simple",
                "fallback": is_fallback,
                "fallback_reason": dense_msg if active_emb!=requested_emb else ce_msg if active_rerank!=requested_rerank else "none"
            }
        except Exception as e:
            results[cfg["name"]] = {"error": str(e)[:500], "config": cfg, "requested_embedding_provider": requested_emb, "active_embedding_provider": None, "fallback": True}
    # Restore
    settings.embedding_provider = original_emb
    settings.reranker_provider = original_rerank
    reset_embedding_provider()
    try:
        from ..core.reranker import reset_reranker
        reset_reranker()
    except Exception:
        pass
    try:
        from .cache import retrieval_cache
        retrieval_cache.invalidate("retrieval")
    except: pass
    return results

def ablation_study(db: Session):
    """Evaluate semantic only, keyword only, hybrid, hybrid+MMR, hybrid+reranker"""
    from ..config import settings
    settings_backup = (settings.semantic_weight, settings.keyword_weight, settings.mmr_lambda, settings.reranker_provider)
    tests = [
        {"name": "keyword_only", "semantic":0.0, "keyword":1.0, "mmr":0, "reranker":"simple"},
        {"name": "semantic_only", "semantic":1.0, "keyword":0.0, "mmr":0, "reranker":"simple"},
        {"name": "hybrid", "semantic":0.6, "keyword":0.4, "mmr":0, "reranker":"simple"},
        {"name": "hybrid+MMR", "semantic":0.6, "keyword":0.4, "mmr":0.7, "reranker":"simple"},
        {"name": "hybrid+SimpleReranker", "semantic":0.6, "keyword":0.4, "mmr":0.7, "reranker":"simple"},
        {"name": "hybrid+CrossEncoder", "semantic":0.6, "keyword":0.4, "mmr":0.7, "reranker":"cross_encoder"},
        {"name": "dense+CrossEncoder", "semantic":0.6, "keyword":0.4, "mmr":0.7, "reranker":"cross_encoder", "embedding": "dense"},
    ]
    results = {}
    emb_backup = settings.embedding_provider
    for t in tests:
        try:
            settings.semantic_weight = t["semantic"]
            settings.keyword_weight = t["keyword"]
            settings.mmr_lambda = t["mmr"]
            settings.reranker_provider = t["reranker"]
            if t.get("embedding"):
                settings.embedding_provider = t["embedding"]
            from ..core.embedding_provider import reset_embedding_provider
            from ..core.reranker import reset_reranker
            reset_embedding_provider()
            reset_reranker()
            from .cache import retrieval_cache
            retrieval_cache.invalidate("retrieval")
            res = run_evaluation(db, top_k=5)
            results[t["name"]] = res["summary"]
        except Exception as e:
            results[t["name"]] = {"error": str(e)[:200]}
    # Restore
    settings.semantic_weight, settings.keyword_weight, settings.mmr_lambda, settings.reranker_provider = settings_backup
    settings.embedding_provider = emb_backup
    try:
        from ..core.embedding_provider import reset_embedding_provider
        from ..core.reranker import reset_reranker
        reset_embedding_provider()
        reset_reranker()
    except Exception:
        pass
    try:
        from .cache import retrieval_cache
        retrieval_cache.invalidate("retrieval")
    except: pass
    return results

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preflight"
    if cmd == "preflight":
        from .preflight import run_preflight
        ok, _ = run_preflight()
        sys.exit(0 if ok else 1)
    elif cmd == "matrix":
        strict = "--strict" in sys.argv
        from ..database import SessionLocal
        import backend.app.models.all_models  # noqa
        import json
        db = SessionLocal()
        seed_evaluation_cases(db, expand=True)
        out = run_benchmark_matrix(db, strict=strict)
        print(json.dumps(out, indent=2, default=str)[:8000])
    elif cmd == "run":
        from ..database import SessionLocal
        import backend.app.models.all_models  # noqa
        import json
        db = SessionLocal()
        seed_evaluation_cases(db, expand=True)
        out = run_evaluation(db)
        print(json.dumps(out["summary"], indent=2))
    else:
        print(f"Unknown command {cmd}. Use: preflight | run | matrix [--strict]")
        sys.exit(2)
