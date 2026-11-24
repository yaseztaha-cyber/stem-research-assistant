import re
import math
from typing import List, Dict, Tuple
from ..config import settings

# --- Claim type patterns ---
CLAIM_TYPE_PATTERNS = {
    "equation": [r"[A-Za-z]\s*=\s*[A-Za-z0-9]", r"P\s*=\s*VI", r"V\s*=\s*IR", r"η\s*=", r"Q\s*=", r"V\s*=\s*S"],
    "number": [r"\d+\.?\d*\s*%", r"\d+\.?\d*\s*W", r"\d+\.?\d*\s*V", r"\d+\.?\d*\s*K", r"approximately \d+"],
    "experimental_result": [r"result", r"measured", r"experiment", r"output increased", r"efficiency", r"found"],
    "definition": [r"is defined as", r"refers to", r"is called", r"means"],
    "causal_claim": [r"causes", r"leads to", r"results in", r"produces", r"increases because", r"decreases because", r"due to"],
    "comparison": [r"compare", r"higher than", r"lower than", r"more than", r"less than", r"versus", r"while.*reports"],
    "interpretation": [r"suggests", r"indicates", r"implies", r"interpret", r"can be understood"],
    "recommendation": [r"should", r"recommend", r"future work", r"optimize"],
}

CAUSAL_PATTERNS = [r"\bcauses\b", r"\bleads to\b", r"\bresults in\b", r"\bproduces\b", r"\bincreases because\b", r"\bdecreases because\b", r"\bdue to\b", r"\bcaused by\b"]

CORRELATION_PATTERNS = [r"correlat", r"associated with", r"related to", r"linked to"]

def classify_claim_type(text: str) -> str:
    low = text.lower()
    # Priority: equation, number strict
    if any(re.search(p, text) for p in CLAIM_TYPE_PATTERNS["equation"]):
        return "equation"
    if any(re.search(p, low) for p in CLAIM_TYPE_PATTERNS["number"]):
        # check if also causal
        if any(re.search(p, low) for p in CAUSAL_PATTERNS):
            return "causal_claim"
        return "number"
    for kind in ["causal_claim", "experimental_result", "definition", "comparison", "recommendation"]:
        pats = CLAIM_TYPE_PATTERNS.get(kind, [])
        if any(re.search(p, low) for p in pats):
            return kind
    if any(re.search(p, low) for p in CLAIM_TYPE_PATTERNS["interpretation"]):
        return "interpretation"
    return "fact"

def extract_numbers(text: str) -> List[Tuple[str, float, str]]:
    """Extract numbers with context: returns (raw, value, unit)"""
    results = []
    # patterns: 14%, 4.2W, 5.2 percent, 0.14 as 14%, etc
    patterns = [
        (r"(\d+\.?\d*)\s*%", "%"),
        (r"(\d+\.?\d*)\s*W\b", "W"),
        (r"(\d+\.?\d*)\s*V\b", "V"),
        (r"(\d+\.?\d*)\s*K\b", "K"),
        (r"(\d+\.?\d*)\s*Ω\b", "Ω"),
        (r"(\d+\.?\d*)\s*percent", "%"),
        (r"(\d+\.?\d*)\s*A\b", "A"),
    ]
    for pat, unit in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            raw = m.group(0)
            try:
                val = float(m.group(1))
                # normalize percent: 14% vs 0.14 -> keep as percent value
                if unit == "%" and val < 1 and "percent" not in raw.lower() and "%" in raw:
                    # Keep raw, but value as percent
                    pass
                results.append((raw.strip(), val, unit))
            except: pass
    return results

def normalize_numeric_value(raw: str, val: float, unit: str) -> float:
    # Convert strings like "14 percent" to 14, "0.14" to 14 if context is percent
    low = raw.lower()
    if "percent" in low and val < 1:
        return val * 100
    return val

def verify_numeric_claim(claim_text: str, retrieved: List[Dict], tolerance: float = 0.05) -> Dict:
    """Verify numeric claim against source numbers"""
    claim_nums = extract_numbers(claim_text)
    if not claim_nums:
        return {"has_numeric": False, "support_status": "not_applicable", "support_score": 0, "details": "no numbers in claim"}
    # collect source numbers
    source_nums = []
    for r in retrieved:
        source_nums.extend(extract_numbers(r["text"]))

    # For each claim number, find closest source with same unit
    best_match = None
    best_diff = float('inf')
    for craw, cval, cunit in claim_nums:
        cval_norm = normalize_numeric_value(craw, cval, cunit)
        for sraw, sval, sunit in source_nums:
            if cunit != sunit:
                continue
            sval_norm = normalize_numeric_value(sraw, sval, sunit)
            diff = abs(cval_norm - sval_norm) / max(abs(sval_norm), 1e-6) if sval_norm!=0 else abs(cval_norm - sval_norm)
            if diff < best_diff:
                best_diff = diff
                best_match = (craw, sraw, cunit, diff, cval_norm, sval_norm)

    if best_match is None:
        # No same-unit source numbers at all
        return {"has_numeric": True, "support_status": "unsupported", "support_score": 0.0, "source_value": None, "generated_value": claim_nums[0][0], "difference": None, "reason": "no matching unit in sources"}

    craw, sraw, unit, diff, cval_norm, sval_norm = best_match
    if diff <= tolerance:
        status = "supported"
        score = 1.0 - diff
    elif diff <= 0.15:
        status = "partially_supported"
        score = 0.6
    else:
        status = "unsupported"
        score = 0.2
        # Check if contradicted: source has very different value (e.g., 12% vs 18%)
        if diff > 0.3:
            status = "contradicted"

    return {
        "has_numeric": True,
        "support_status": status,
        "support_score": round(score,3),
        "source_value": sraw,
        "generated_value": craw,
        "difference": round(diff,3),
        "unit": unit,
        "source_normalized": sval_norm,
        "generated_normalized": cval_norm,
    }

def verify_equation_claim(claim_text: str, retrieved: List[Dict]) -> Dict:
    """Verify equation exists in retrieved evidence with same concept/context"""
    # extract equation-like patterns from claim
    eq_pats = re.findall(r"[A-Za-zημΔ]\s*=\s*[A-Za-z0-9ΔημΩ\*\s\/\+\-\.\^\(\)]+", claim_text)
    if not eq_pats:
        return {"has_equation": False, "support_status": "not_applicable", "support_score": 0}
    # Also check known equations
    known = ["P = VI", "V = IR", "V = S * DeltaT", "Q = mcΔT", "η = Pout / Pin", "P = I^2 R"]
    claim_eq = eq_pats[0].strip()
    # normalize spaces
    norm_claim = re.sub(r"\s+", "", claim_eq).lower()
    # also normalized without * for leniency (VI vs V*I)
    norm_claim_no_star = norm_claim.replace("*","")
    best = None
    # helper to extract variable sets
    def vars_of(eq: str):
        parts = eq.split("=")
        if len(parts)!=2:
            return set(), set()
        left = re.findall(r"[A-Za-zΔημ]+", parts[0].lower())
        right = re.findall(r"[A-Za-zΔημ]+", parts[1].lower())
        # For right side, split concatenated like "vi" into "v","i" if needed? Treat each letter as var if right side is short
        # e.g., "vi" -> should be {"v","i"} not {"vi"}
        # If right side token is like "vi" and contains known vars, split
        expanded = set()
        for tok in right:
            if tok.lower() == "vi":
                expanded.update(["v","i"])
            elif tok.lower() == "ir":
                expanded.update(["i","r"])
            else:
                # split each character if token length 2 and both are single letters? e.g., "s*delta" already split
                if len(tok)==2 and tok.isalpha() and tok.lower() not in ["do","is","as"]:
                    # check if both letters are known variables
                    if all(c in "pvirsqmc" for c in tok.lower()):
                        expanded.update(list(tok.lower()))
                    else:
                        expanded.add(tok.lower())
                else:
                    expanded.add(tok.lower())
        left_set = set([l.lower() for l in left])
        return left_set, expanded

    claim_left, claim_right = vars_of(norm_claim)
    for r in retrieved:
        # find equations in source
        source_eqs = re.findall(r"[A-Za-zημΔ]\s*=\s*[A-Za-z0-9ΔημΩ\*\s\/\+\-\.\^\(\)]+", r["text"])
        for se in source_eqs:
            norm_src = re.sub(r"\s+", "", se).lower()
            norm_src_no_star = norm_src.replace("*","")
            # exact or substring match (strict)
            if norm_claim == norm_src or norm_claim in norm_src or norm_src in norm_claim:
                best = (claim_eq, se, r)
                break
            if norm_claim_no_star == norm_src_no_star or norm_claim_no_star in norm_src_no_star or norm_src_no_star in norm_claim_no_star:
                # lenient without star
                best = (claim_eq, se, r)
                break
            # variable set match lenient
            src_left, src_right = vars_of(norm_src)
            if claim_left and claim_left == src_left and claim_right and claim_right == src_right:
                best = (claim_eq, se, r)
                break
            # also check known
            for k in known:
                nk = re.sub(r"\s+", "", k).lower().replace("*","")
                if norm_claim_no_star == nk and nk == norm_src_no_star:
                    best = (claim_eq, se, r)
                    break
        if best:
            break
    if best:
        return {"has_equation": True, "support_status": "supported", "support_score": 0.95, "source_equation": best[1], "generated_equation": best[0], "evidence": {"document": best[2]["document_name"], "page": best[2]["page_number"], "chunk_id": best[2]["chunk_id"]}}
    else:
        # Check if claim equation is mathematically plausible but not in source -> unsupported in grounded mode
        return {"has_equation": True, "support_status": "unsupported", "support_score": 0.2, "source_equation": None, "generated_equation": claim_eq, "reason": "equation not found in retrieved evidence"}

def detect_causal_claim(text: str) -> Dict:
    has_causal = any(re.search(p, text.lower()) for p in CAUSAL_PATTERNS)
    has_correlation = any(re.search(p, text.lower()) for p in CORRELATION_PATTERNS)
    # If claim asserts causation but source only has correlation, it's risky
    return {"has_causal": has_causal, "has_correlation": has_correlation}

def verify_causal_claim(claim_text: str, retrieved: List[Dict]) -> Dict:
    causal_info = detect_causal_claim(claim_text)
    if not causal_info["has_causal"]:
        return {"is_causal": False, "support_status": "not_applicable", "support_score": 0}
    # Check if any retrieved source establishes causation vs correlation
    source_texts = " ".join([r["text"].lower() for r in retrieved])
    source_has_causal = any(re.search(p, source_texts) for p in CAUSAL_PATTERNS)
    source_has_correlation = any(re.search(p, source_texts) for p in CORRELATION_PATTERNS)
    if source_has_causal:
        # source does claim causation, check support
        return {"is_causal": True, "support_status": "supported", "support_score": 0.8, "source_evidence": "causal language in source"}
    elif source_has_correlation:
        # source only correlation, claim overstates
        return {"is_causal": True, "support_status": "unsupported", "support_score": 0.2, "reason": "source reports correlation, not causation; claiming causation overstates evidence", "corrected": "The source reports a positive correlation; it does not establish causation."}
    else:
        return {"is_causal": True, "support_status": "unsupported", "support_score": 0.1, "reason": "no causal or correlation evidence in sources"}

def extract_claims(answer_text: str) -> List[Dict]:
    """Split answer into claims (sentences) and classify as source or generated + claim_type"""
    def _merge_tags_into_prev(tagged: str) -> None:
        """v0.5: tag-only sentences ("[DERIVED from P = VI] [SOURCE: ...]")
        belong to the previous claim — merge instead of dropping."""
        if not claims:
            return
        prev = claims[-1]
        if "[generated]" in tagged:
            prev["type"] = "generated"
        elif "[derived" in tagged:
            prev["type"] = "derived"
            if prev.get("claim_type") not in ("equation", "number"):
                prev["claim_type"] = "derived"
        elif "[source" in tagged and prev["type"] == "generated" and not any(
                m in prev["text"].lower() for m in ["according to", "the document", "the paper"]):
            # Only upgrade bare-generated to source when the tag is the
            # sole content (explicit provenance for the prior sentence)
            prev["type"] = "source"

    sentences = re.split(r"(?<=[.!?])\s+", answer_text.strip())
    claims=[]
    for sent in sentences:
        if not sent.strip():
            continue
        # Allow short claims if they contain equations or numbers (e.g., "P = VI")
        stripped = sent.strip()
        if len(stripped)<10 and not re.search(r"[A-Za-z]\s*=\s*|^\d+\.?\d*\s*[A-Z%]", stripped):
            _merge_tags_into_prev(stripped.lower())
            continue
        low = sent.lower()
        ctype = "generated"
        # Check for DERIVED first (higher priority for derived reasoning)
        if "[derived" in low:
            ctype = "derived"
        elif "[source" in low or "source:" in low or "according to" in low or "the document" in low or "the paper" in low or "experimental results" in low or "page" in low and "section" in low:
            if "[generated]" in low:
                ctype = "generated"
            elif "[derived" in low:
                ctype = "derived"
            else:
                if "[source" in low:
                    ctype = "source"
                elif any(marker in low for marker in ["according to", "the document", "the paper", "results show", "experiment", "document defines"]):
                    ctype = "source"
        if "[generated]" in low:
            ctype = "generated"
            sent = sent.replace("[GENERATED]", "").replace("[generated]", "").strip()
        if "[derived" in low:
            ctype = "derived"
            sent = re.sub(r"\[DERIVED[^\]]*\]", "", sent, flags=re.IGNORECASE).strip()
        if "[source" in low:
            sent = re.sub(r"\[SOURCE[^\]]*\]", "", sent, flags=re.IGNORECASE).strip()
        clean = sent.strip()
        if len(clean)<10 and not re.search(r"[A-Za-z]\s*=\s*|^\d+\.?\d*\s*[A-Z%]", clean):
            _merge_tags_into_prev(low)
            continue
        claim_type = classify_claim_type(clean)
        # For derived, override claim_type to derived if not already
        if ctype == "derived" and claim_type not in ("equation", "number"):
            claim_type = "derived"
        claims.append({"text": clean, "type": ctype, "claim_type": claim_type})
    return claims

def evaluate_grounding(claims: List[Dict], retrieved: List[Dict], answer_text: str) -> Dict:
    """Compute grounding score based on retrieval relevance, evidence coverage, claim-source alignment, contradiction, source quality"""
    if not claims:
        return {"score": 0, "percentage": 0, "factors": {"retrieval_relevance":0, "evidence_coverage":0, "claim_source_alignment":0, "contradiction_handled":1.0, "source_quality":0.85, "unsupported_claim_rate":0, "total_claims":0, "source_claims":0, "generated_claims":0}, "explanation": "No claims extracted"}

    total = len(claims)
    source_claims = [c for c in claims if c["type"]=="source"]
    generated_claims = [c for c in claims if c["type"]=="generated"]

    if retrieved:
        avg_retrieval = sum(r.get("retrieval_score",0) for r in retrieved[:3]) / min(3, len(retrieved))
    else:
        avg_retrieval = 0

    # evidence coverage with verification: use detailed verification for stricter types
    evidence_coverage = 0
    if source_claims and retrieved:
        matched=0
        for claim in source_claims:
            # stricter verification for numbers/equations/causal
            ctype = claim.get("claim_type","fact")
            verified = False
            support_status = "unsupported"
            if ctype in ("number","experimental_result"):
                res = verify_numeric_claim(claim["text"], retrieved)
                if res["support_status"] in ("supported","partially_supported"):
                    verified = True
                support_status = res["support_status"]
            elif ctype == "equation":
                res = verify_equation_claim(claim["text"], retrieved)
                verified = res["support_status"] == "supported"
                support_status = res["support_status"]
            elif ctype == "causal_claim":
                res = verify_causal_claim(claim["text"], retrieved)
                verified = res["support_status"] == "supported"
                support_status = res["support_status"]
            else:
                # generic term overlap
                terms = set(re.findall(r"\w+", claim["text"].lower()))
                for r in retrieved[:5]:
                    r_terms = set(re.findall(r"\w+", r["text"].lower()))
                    overlap = len(terms.intersection(r_terms)) / max(len(terms),1)
                    if overlap>0.25:
                        verified = True
                        support_status = "supported"
                        break
                    elif overlap>0.15:
                        support_status = "partially_supported"
                # if partially supported count as half
                if support_status == "partially_supported":
                    matched += 0.5
                    verified = False  # don't double count
                if verified:
                    matched+=1
                    continue
                if support_status == "partially_supported":
                    continue
                # else not matched

            if verified:
                matched += 1 if ctype not in ("number","equation","causal_claim") else 1  # already counted above for generic; for strict types we haven't counted yet
                # For strict types, matched increment handled inside? Actually for strict we set verified True but not yet added; need to add
                # To avoid double, we increment only if not already
                # Simplify: for strict, if verified, count
                if ctype in ("number","equation","causal_claim") and verified:
                    # we already matched variable? No, generic path not taken. So count now.
                    # But we already did? Let's just ensure:
                    pass
            # For strict types where verified True but we didn't increment due to generic path skipping, increment
            # Actually strict path: we set verified based on numeric/equation, but not yet matched count
            # So if ctype in strict and verified, increment
            if ctype in ("number","equation","causal_claim") and verified:
                # check if already counted: we didn't, so add
                # But for number/equation we returned verified, need to add if not already added via generic half
                # Since we bypass generic counting, just add
                # We need to avoid double counting: for strict, generic not executed beyond half, so safe to add
                # But we already added 0 for partial; for full verified, add 1
                # However for strict types, we didn't increment at all yet, so add 1
                # For number/equation/causal that was verified, count = 1
                # But we have logic that for strict types, we set verified but matched still 0, so we need to increment
                # Let's track if we already incremented: for strict types we set verified but didn't increment matched in generic branch
                # So increment now if verified and not already counted
                # We'll just if ctype in strict and verified: matched +=1
                # But this would double if we already did for generic? For strict we didn't go generic, so ok
                pass

        # Fix counting: recalc properly with correct logic
        # The above incremental logic got tangled; recompute cleanly
        matched = 0
        for claim in source_claims:
            ctype = claim.get("claim_type","fact")
            if ctype in ("number","experimental_result"):
                res = verify_numeric_claim(claim["text"], retrieved)
                if res["support_status"] in ("supported","partially_supported"):
                    matched += 1 if res["support_status"]=="supported" else 0.5
            elif ctype == "equation":
                res = verify_equation_claim(claim["text"], retrieved)
                if res["support_status"] == "supported":
                    matched += 1
                elif res["support_status"] == "partially_supported":
                    matched += 0.5
            elif ctype == "causal_claim":
                res = verify_causal_claim(claim["text"], retrieved)
                if res["support_status"] == "supported":
                    matched += 1
            else:
                terms = set(re.findall(r"\w+", claim["text"].lower()))
                for r in retrieved[:5]:
                    r_terms = set(re.findall(r"\w+", r["text"].lower()))
                    overlap = len(terms.intersection(r_terms)) / max(len(terms),1)
                    if overlap>0.25:
                        matched+=1
                        break
                    elif overlap>0.15:
                        matched+=0.5
                        break
        evidence_coverage = matched / len(source_claims) if source_claims else 0.5
        evidence_coverage = min(evidence_coverage, 1.0)
    elif not source_claims:
        evidence_coverage = 0.5

    alignment = evidence_coverage * 0.9 + avg_retrieval *0.1

    contradiction = 1.0
    if "disagree" in answer_text.lower() or "conflict" in answer_text.lower() or "contradiction" in answer_text.lower():
        contradiction = 0.9
    else:
        nums = []
        for r in retrieved[:5]:
            nums.extend(re.findall(r"(\d+\.?\d*)\s*%", r["text"]))
        if len(set(nums))>1:
            contradiction = 0.7
        # also check for conflicting efficiency values
        eff_vals = []
        for r in retrieved[:5]:
            eff_vals.extend(re.findall(r"efficiency\s*[=:]\s*(\d+\.?\d*)\s*%", r["text"], re.IGNORECASE))
            eff_vals.extend(re.findall(r"(\d+\.?\d*)\s*%\s*efficiency", r["text"], re.IGNORECASE))
        if len(set(eff_vals))>1:
            contradiction = 0.6

    unsupported_rate = 1 - evidence_coverage if source_claims else 0
    unsupported_penalty = unsupported_rate * 0.3
    source_quality = 0.85

    score = (
        avg_retrieval * 0.25 +
        evidence_coverage * 0.35 +
        alignment * 0.2 +
        contradiction * 0.1 +
        source_quality * 0.1
    ) - unsupported_penalty

    score = max(0, min(1, score))

    return {
        "score": round(score,3),
        "percentage": int(round(score*100)),
        "factors": {
            "retrieval_relevance": round(avg_retrieval,3),
            "evidence_coverage": round(evidence_coverage,3),
            "claim_source_alignment": round(alignment,3),
            "contradiction_handled": round(contradiction,3),
            "source_quality": round(source_quality,3),
            "unsupported_claim_rate": round(unsupported_rate,3),
            "total_claims": total,
            "source_claims": len(source_claims),
            "generated_claims": len(generated_claims),
        },
        "explanation": f"Grounding based on {len(source_claims)} source claims vs {len(generated_claims)} generated. Retrieval relevance {avg_retrieval:.2f}, coverage {evidence_coverage:.2f}."
    }

def verify_citations(answer_text: str, retrieved: List[Dict]) -> Dict:
    """Check citation existence and validity - legacy wrapper, now also returns per-citation validation"""
    detailed = verify_citations_v2(answer_text, retrieved)
    # map to legacy shape for backward compat
    return {
        "total_found": detailed["total_found"],
        "valid": detailed["valid_count"],
        "invalid": detailed["invalid_count"],
        "has_citations": detailed["has_citations"],
        "retrieved_doc_pages": detailed["retrieved_doc_pages"],
        "details": detailed["citations"]
    }

def verify_citations_v2(answer_text: str, retrieved: List[Dict]) -> Dict:
    """Validate each citation: document exists, page exists, section exists, chunk exists, claim supported"""
    citation_pattern = r"\[SOURCE[^\]]*\]"
    found = re.findall(citation_pattern, answer_text, flags=re.IGNORECASE)
    retrieved_map = {(r.get("document_name"), str(r.get("page_number"))): r for r in retrieved if r.get("document_name")}
    retrieved_chunks = {r.get("chunk_id"): r for r in retrieved if r.get("chunk_id")}
    retrieved_docs = set([r.get("document_name") for r in retrieved if r.get("document_name")])

    citations = []
    valid_count = 0
    partial_count = 0
    invalid_count = 0

    for cit in found:
        doc_match = re.search(r"([a-zA-Z0-9_\-]+\.[a-z]+)", cit)
        page_match = re.search(r"p\.?\s*(\d+)", cit, re.IGNORECASE)
        chunk_match = re.search(r"chunk[:\s]*([a-f0-9\-]+)", cit, re.IGNORECASE)
        sec_match = re.search(r"§\s*([^;\]]+)", cit)

        doc_name = doc_match.group(1) if doc_match else None
        page = page_match.group(1) if page_match else None
        chunk_id = chunk_match.group(1) if chunk_match else None

        # Determine status
        status = "INVALID"
        reason = []
        evidence = None

        if doc_name and doc_name not in retrieved_docs:
            reason.append(f"document '{doc_name}' not in retrieved evidence")
        elif doc_name and doc_name in retrieved_docs:
            # doc exists
            if page:
                key = (doc_name, page)
                if key not in retrieved_map:
                    reason.append(f"page {page} not found for document {doc_name} in retrieved")
                    status = "PARTIAL"
                else:
                    evidence = retrieved_map[key]
                    status = "VALID"
            else:
                # page not specified but doc matches -> partial
                status = "PARTIAL"
                reason.append("page not specified")
        elif not doc_name and "source" in cit.lower():
            # generic source tag without doc -> partial
            status = "PARTIAL"
            reason.append("generic SOURCE tag without specific provenance")
        else:
            reason.append("unparsable citation")

        # chunk validation
        if chunk_id:
            if chunk_id not in retrieved_chunks:
                reason.append(f"chunk {chunk_id[:8]} not in retrieved")
                if status == "VALID":
                    status = "PARTIAL"
            else:
                evidence = retrieved_chunks[chunk_id]
                status = "VALID"
                reason = []

        if status == "VALID":
            valid_count += 1
        elif status == "PARTIAL":
            partial_count += 1
        else:
            invalid_count += 1

        citations.append({
            "raw": cit,
            "document": doc_name,
            "page": page,
            "chunk_id": chunk_id,
            "section": sec_match.group(1).strip() if sec_match else None,
            "status": status,
            "reason": "; ".join(reason) if reason else "ok",
            "evidence": {"document_name": evidence["document_name"], "page_number": evidence["page_number"]} if evidence else None
        })

    return {
        "total_found": len(found),
        "valid_count": valid_count,
        "partial_count": partial_count,
        "invalid_count": invalid_count,
        "has_citations": len(found)>0,
        "retrieved_doc_pages": list(retrieved_map.keys()),
        "citations": citations,
        "citation_accuracy": round(valid_count / max(len(found),1),3),
        "citation_precision": round(valid_count / max(len(found),1),3),
        "citation_recall": round(valid_count / max(len(retrieved),1),3) if retrieved else 0
    }

def hallucination_checks(answer_text: str, retrieved: List[Dict], claims: List[Dict]) -> Dict:
    """Multiple checks: retrieval relevance, claim-source alignment, citation existence, unsupported claims, contradiction"""
    grounding = evaluate_grounding(claims, retrieved, answer_text)
    citation_check = verify_citations(answer_text, retrieved)
    # also v2 detailed
    citation_v2 = verify_citations_v2(answer_text, retrieved)

    # unsupported claim detection with support states
    unsupported = []
    partially = []
    supported = []
    for c in claims:
        if c["type"]=="source":
            # use verification matching
            ctype = c.get("claim_type","fact")
            support_status = "unsupported"
            support_score = 0
            if ctype in ("number","experimental_result"):
                res = verify_numeric_claim(c["text"], retrieved)
                support_status = res["support_status"]
                support_score = res.get("support_score",0)
            elif ctype == "equation":
                res = verify_equation_claim(c["text"], retrieved)
                support_status = res["support_status"]
                support_score = res.get("support_score",0)
            elif ctype == "causal_claim":
                res = verify_causal_claim(c["text"], retrieved)
                support_status = res["support_status"]
                support_score = res.get("support_score",0)
            else:
                # generic overlap
                max_overlap = 0
                for r in retrieved:
                    overlap = len(set(c["text"].lower().split()).intersection(set(r["text"].lower().split()))) / max(len(c["text"].split()),1)
                    max_overlap = max(max_overlap, overlap)
                if max_overlap > 0.25:
                    support_status = "supported"
                    support_score = max_overlap
                elif max_overlap > 0.15:
                    support_status = "partially_supported"
                    support_score = max_overlap
                else:
                    support_status = "unsupported"
                    support_score = max_overlap

            c["support_status"] = support_status
            c["support_score"] = round(support_score,3)

            if support_status == "unsupported":
                unsupported.append(c["text"])
            elif support_status == "partially_supported":
                partially.append(c["text"])
            elif support_status == "supported":
                supported.append(c["text"])
            # contradicted case handled inside numeric verification
            if support_status == "contradicted":
                unsupported.append(c["text"] + " [CONTRADICTED]")
        elif c["type"]=="derived":
            # Derived reasoning: validated via math, not source strict
            try:
                from .math_validation import full_math_validation
                import re as _re
                eq_match = _re.search(r"[A-Za-z]\s*=\s*[A-Za-z0-9\*\s\/\(\)Δη]+", c["text"])
                if eq_match:
                    res = full_math_validation(eq_match.group(0))
                    if res.get("syntax",{}).get("syntax_valid"):
                        support_status="supported"
                        support_score=0.85
                    else:
                        support_status="partially_supported"
                        support_score=0.5
                else:
                    has_eq_in_source = any("=" in r["text"] for r in retrieved)
                    if has_eq_in_source and any(k in c["text"].lower() for k in ["doubles","halves","increases","proportional"]):
                        support_status="supported"
                        support_score=0.75
                    else:
                        support_status="partially_supported"
                        support_score=0.4
            except Exception:
                support_status="partially_supported"
                support_score=0.5
            c["support_status"]=support_status
            c["support_score"]=round(support_score,3)
            if support_status=="supported":
                supported.append(c["text"] + " [DERIVED]")
            elif support_status=="partially_supported":
                partially.append(c["text"] + " [DERIVED]")
            else:
                unsupported.append(c["text"] + " [DERIVED]")

    # contradiction detection for final answer
    contradiction_note = None
    if grounding["factors"]["contradiction_handled"] < 0.8:
        contradiction_note = "Potential disagreement detected between sources; see evidence explorer for details."

    return {
        "grounding": grounding,
        "citations": citation_check,
        "citations_v2": citation_v2,
        "unsupported_claims": unsupported,
        "partially_supported": partially,
        "supported_claims": supported,
        "unsupported_rate": len(unsupported)/max(len([c for c in claims if c["type"]=="source"]),1) if claims else 0,
        "is_grounded": grounding["score"]>settings.grounding_threshold and len(unsupported)==0 and citation_check["has_citations"] or grounding["score"]>0.75,
        "contradiction_note": contradiction_note,
        "claim_types": {ct: len([c for c in claims if c.get("claim_type")==ct]) for ct in set([c.get("claim_type","fact") for c in claims])}
    }

def verify_claims_pipeline(answer_text: str, retrieved: List[Dict]) -> Dict:
    """Full pipeline: extract → classify → verify each claim → citation validation → final"""
    claims = extract_claims(answer_text)
    checks = hallucination_checks(answer_text, retrieved, claims)
    # Attach per-claim evidence
    for c in claims:
        # find evidence ids
        ev = []
        for r in retrieved:
            overlap = len(set(c["text"].lower().split()).intersection(set(r["text"].lower().split()))) / max(len(c["text"].split()),1)
            if overlap > 0.15:
                ev.append({"document": r["document_name"], "page": r["page_number"], "chunk_id": r["chunk_id"], "retrieval_score": r.get("retrieval_score")})
                if len(ev)>=2:
                    break
        c["evidence_ids"] = [e["chunk_id"] for e in ev]
        c["evidence"] = ev
        # ensure support fields
        if "support_status" not in c:
            c["support_status"] = "partially_supported" if c["type"]=="source" else "not_applicable"
        if "support_score" not in c:
            c["support_score"] = 0.5
        c["citation_status"] = "VALID" if c["type"]=="source" and checks["citations_v2"]["valid_count"]>0 else "INVALID" if c["type"]=="source" else "not_applicable"

    return {
        "claims": claims,
        "grounding": checks["grounding"],
        "citations": checks["citations_v2"],
        "hallucination": checks,
        "is_grounded": checks["is_grounded"]
    }
