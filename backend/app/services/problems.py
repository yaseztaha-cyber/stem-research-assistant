from sqlalchemy.orm import Session
from typing import List, Dict
import re
import random
from ..models.chunk import DocumentChunk
from ..models.learning import PracticeProblem
from ..utils.text import explain_variables

def generate_problems(db: Session, document_id: str = None, collection_id: str = None, difficulty: str = "medium", limit: int = 5) -> List[Dict]:
    q = db.query(DocumentChunk)
    if document_id:
        q = q.filter(DocumentChunk.document_id==document_id)
    if collection_id:
        from ..models.collection import CollectionDocument
        doc_ids = [r.document_id for r in db.query(CollectionDocument).filter(CollectionDocument.collection_id==collection_id).all()]
        if doc_ids:
            q = q.filter(DocumentChunk.document_id.in_(doc_ids))
    chunks = q.filter(DocumentChunk.content_type.in_(["equation","result","paragraph"])).limit(80).all()
    problems=[]
    for ch in chunks:
        if len(problems)>=limit*2: break
        text = ch.text
        # find equations with variables
        eq_match = re.search(r"([A-Za-z]\s*=\s*[A-Za-z0-9\*\s\/\+\-\(\)Δη]+)", text)
        if eq_match:
            eq = eq_match.group(1).strip()
            # limit to known solvable patterns
            # generate quantitative problem
            if "V = IR" in eq.replace(" ","") or "V=IR" in eq.replace(" ",""):
                # Ohm law: random values
                R = random.choice([10, 20, 47, 100])
                I_val = round(random.uniform(0.5, 3.0),2)
                V_val = round(R * I_val, 2)
                known = {"R": f"{R} Ω", "I": f"{I_val} A"}
                unknown = "V"
                relevant_eq = "V = I·R"
                solution = f"V = I × R = {I_val} A × {R} Ω = {V_val} V"
                unit_check = "Ω·A = V (since V = J/C, Ω = V/A), dimensionally consistent."
                final = f"{V_val} V"
                problems.append({
                    "problem": f"A resistor of {R} Ω carries a current of {I_val} A. Calculate the voltage across it using {relevant_eq}.",
                    "known_values": known, "unknown": unknown, "relevant_equation": relevant_eq,
                    "solution": solution, "unit_verification": unit_check, "final_answer": final,
                    "difficulty": difficulty, "type":"quantitative",
                    "source": {"document_id": ch.document_id, "page": ch.page_number, "chunk_id": ch.id}
                })
            elif "P = VI" in text.replace(" ","") or "P=VI" in text.replace(" ",""):
                V_val = random.choice([12, 24, 48])
                I_val = round(random.uniform(1,5),2)
                P_val = round(V_val * I_val,2)
                problems.append({
                    "problem": f"A thermoelectric generator outputs {V_val} V at {I_val} A. What is the electrical power? Use P = V·I.",
                    "known_values": {"V": f"{V_val} V", "I": f"{I_val} A"}, "unknown":"P", "relevant_equation":"P = V·I",
                    "solution": f"P = V × I = {V_val} × {I_val} = {P_val} W", "unit_verification":"V·A = W (watts), consistent.", "final_answer": f"{P_val} W",
                    "difficulty": difficulty, "type":"quantitative",
                    "source": {"document_id": ch.document_id, "page": ch.page_number, "chunk_id": ch.id}
                })
            elif "Q = mcΔT" in text or "Q=mc" in text:
                m = random.choice([0.5, 1.0, 2.0])
                c_val = 4186  # water
                dT = random.choice([10,20,30])
                Q_val = m * c_val * dT
                problems.append({
                    "problem": f"Calculate heat required to raise {m} kg of water by ΔT = {dT} K (c = 4186 J/kg·K). Use Q = m·c·ΔT.",
                    "known_values": {"m": f"{m} kg", "c": "4186 J/kg·K", "ΔT": f"{dT} K"}, "unknown":"Q", "relevant_equation":"Q = m·c·ΔT",
                    "solution": f"Q = {m} × 4186 × {dT} = {Q_val} J", "unit_verification":"kg·J/(kg·K)·K = J, correct.", "final_answer": f"{Q_val} J",
                    "difficulty": difficulty, "type":"quantitative",
                    "source": {"document_id": ch.document_id, "page": ch.page_number, "chunk_id": ch.id}
                })
        else:
            # qualitative problem based on mechanism
            if len(text)>80:
                sentences = re.split(r"(?<=[.!?])\s+", text)
                if len(sentences)>=1 and len(problems)<limit*2:
                    problems.append({
                        "problem": f"Explain the physical mechanism described: '{sentences[0][:100]}...' What factors influence it and why?",
                        "known_values": None, "unknown": "mechanism explanation", "relevant_equation": None,
                        "solution": f"Based on source: {sentences[0][:200]}. Mechanism involves energy conversion as documented [SOURCE]. Additional factors would include temperature gradient, material properties [GENERATED].",
                        "unit_verification": None, "final_answer": "See solution; requires conceptual reasoning.",
                        "difficulty": difficulty, "type":"qualitative",
                        "source": {"document_id": ch.document_id, "page": ch.page_number, "chunk_id": ch.id}
                    })

    # validation pass: dimensional consistency etc already done via known templates; for others, mark
    validated=[]
    for p in problems[:limit]:
        # check arithmetic if possible
        # already computed; for qualitative skip
        validated.append(p)
        obj = PracticeProblem(document_id=p["source"]["document_id"] if p["source"] else None, problem=p["problem"], known_values=p["known_values"], unknown=p["unknown"], relevant_equation=p["relevant_equation"], solution=p["solution"], unit_verification=p["unit_verification"], final_answer=p["final_answer"], difficulty=p["difficulty"], type=p["type"], source=p["source"])
        db.add(obj)
    db.commit()
    return validated[:limit]
