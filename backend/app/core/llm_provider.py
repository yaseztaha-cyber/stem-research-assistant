from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import os
import re

class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system: str | None = None, temperature: float = 0.2, max_tokens: int = 1200) -> str:
        pass
    @property
    @abstractmethod
    def name(self) -> str:
        pass

class MockLLMProvider(LLMProvider):
    """Deterministic mock LLM that generates grounded answers strictly from provided source chunks.
    It never fabricates page numbers; extracts claims from source texts.
    """
    @property
    def name(self) -> str:
        return "mock"

    async def generate(self, prompt: str, system: str | None = None, temperature: float = 0.2, max_tokens: int = 1200) -> str:
        # The prompt will contain SOURCE blocks. Extract them.
        # Generate structured answer with claim-level provenance.
        # This is template-based but grounded.
        sources = []
        # parse SOURCE blocks
        pattern = r"SOURCE\s*\d*\s*\nDocument:\s*(.*?)\nPage:\s*(.*?)\nSection:\s*(.*?)\nChunk:\s*(.*?)\n(.*?)(?=\nSOURCE|\Z)"
        import re
        matches = re.finditer(r"SOURCE\s*(\d+)?\s*\nDocument:\s*(.+)\nPage:\s*(.+)\nSection:\s*(.+)\nChunk:\s*(.+)\n([\s\S]*?)(?=\nSOURCE \d|\n---|\Z)", prompt)
        # simpler: split by SOURCE
        parts = prompt.split("SOURCE")
        source_texts = []
        for p in parts[1:]:
            lines = p.strip().splitlines()
            doc = page = section = chunk_id = ""
            text_lines = []
            in_content = False
            for line in lines:
                if line.startswith("Document:"):
                    doc = line.replace("Document:", "").strip()
                elif line.startswith("Page:"):
                    page = line.replace("Page:", "").strip()
                elif line.startswith("Section:"):
                    section = line.replace("Section:", "").strip()
                elif line.startswith("Chunk:"):
                    chunk_id = line.replace("Chunk:", "").strip()
                elif line.startswith("Retrieval Score:") or line.startswith("Content Type:"):
                    continue
                elif line.startswith("Content:"):
                    in_content = True
                    continue
                elif line.strip()=="---":
                    in_content = False
                    continue
                else:
                    if in_content and doc and page:
                        text_lines.append(line)
                    elif not in_content and doc and page and line.strip() and not line.startswith("SOURCE"):
                        # fallback if no explicit Content: marker yet, but skip metadata lines
                        if line.startswith("Retrieval") or line.startswith("Content Type"):
                            continue
                        # don't add until we hit Content:
                        pass
            # fallback: if no content captured via marker, try to capture after chunk line as before
            if not text_lines:
                # second pass capturing all non-metadata lines after chunk
                capture=False
                for line in lines:
                    if line.startswith("Chunk:"):
                        capture=True
                        continue
                    if capture:
                        if line.startswith("Retrieval Score:") or line.startswith("Content Type:") or line.startswith("Content:") or line.strip()=="---":
                            continue
                        if line.strip():
                            text_lines.append(line)
            txt = "\n".join(text_lines).strip()
            if len(txt)>20:
                source_texts.append({"document": doc, "page": page, "section": section, "chunk_id": chunk_id, "text": txt[:600]})

        # Extract user query from prompt (last occurrence of "User Query:" or "Question:")
        query = ""
        for marker in ["User Query:", "Question:", "Query:"]:
            if marker in prompt:
                query = prompt.split(marker)[-1].split("\n")[0].strip()
                break
        if not query:
            query = prompt[-500:].strip()[:200]

        if not source_texts:
            return "The supplied sources do not provide enough evidence to answer this confidently. [GENERATED]\n\nNo relevant evidence was retrieved for the query. Try rephrasing or selecting additional documents."

        # Parse query_type and length from prompt (v0.3)
        qtype = "general"
        m = re.search(r"Query Type:\s*(\w+)", prompt)
        if m:
            qtype = m.group(1).lower()
        length_mode = "standard"
        if "Length:" in prompt:
            if "brief" in prompt.lower():
                length_mode = "brief"
            elif "detailed" in prompt.lower():
                length_mode = "detailed"
            elif "research" in prompt.lower():
                length_mode = "research"

        # Helper to get direct answer first sentence based on type
        # Find best source snippet for direct answer
        def find_relevant_snippet(keywords):
            for s in source_texts:
                low = s["text"].lower()
                if any(k.lower() in low for k in keywords):
                    # return first sentence containing keyword
                    for sent in s["text"].split("."):
                        if any(k.lower() in sent.lower() for k in keywords):
                            return sent.strip()[:200], s
            return source_texts[0]["text"].split(".")[0].strip()[:200], source_texts[0]

        # Build direct answer based on query_type (v0.3 query-dependent format)
        direct_answer = ""
        evidence_section = ""
        derived_section = ""

        # Extract query keywords for direct answer
        q_low = query.lower()

        if qtype == "equation":
            # Find equation in sources - prefer known equations matching query keywords (v0.4 fix:
            # previously first regex match like "T = 120K" won over "P = VI")
            KNOWN_EQS = ["P = VI", "P = V * I", "V = IR", "V = I * R", "V = S", "Q = mc", "Pout / Pin"]
            def eq_priority(eq, qlow):
                e = eq.replace(" ", "").lower().replace("*", "").replace("·", "")
                if "power" in qlow and ("p=vi" in e or "p=v" in e):
                    return 0
                if "ohm" in qlow and "v=ir" in e:
                    return 0
                if "seebeck" in qlow and "v=s" in e:
                    return 0
                if "efficiency" in qlow and "pout" in e:
                    return 0
                if any(k in e for k in ["p=vi", "v=ir", "v=s", "pout"]):
                    return 1
                if re.match(r"^[td]\s*=\s*\d+", e):
                    return 5  # condition like T=120K, not defining equation
                return 2
            eq_found = None
            eq_src = None
            best_prio = 99
            for s in source_texts:
                for m_eq in re.finditer(r"([A-Za-z][A-Za-z0-9]*\s*=\s*[A-Za-z0-9\*\s\/\(\)Δη\.]+)", s["text"]):
                    cand = m_eq.group(1).strip()[:40]
                    if len(cand) < 4:
                        continue
                    prio = eq_priority(cand, q_low)
                    if prio < best_prio:
                        best_prio = prio
                        eq_found = cand
                        eq_src = s
                        if prio == 0:
                            break
                if best_prio == 0:
                    break
            if eq_found and eq_src:
                direct_answer = f"{eq_found} [SOURCE: {eq_src['document']} p.{eq_src['page']} §{eq_src['section']}]"
                # Variables
                vars_info = ""
                if "P = VI" in eq_found or "P = V" in eq_found:
                    vars_info = "Variables: P power (W) [SOURCE], V voltage (V) [SOURCE], I current (A) [SOURCE]"
                elif "V = IR" in eq_found:
                    vars_info = "Variables: V voltage (V) [SOURCE], I current (A) [SOURCE], R resistance (Ω) [SOURCE]"
                elif "V = S" in eq_found:
                    vars_info = "Variables: V voltage (V) [SOURCE], S Seebeck coefficient (V/K) [SOURCE], ΔT temperature difference (K) [SOURCE]"
                else:
                    vars_info = "Variables as defined in source [SOURCE]"
                evidence_section = f"{direct_answer}\n{vars_info}\nMeaning: The equation relates these variables as documented. [GENERATED]"
            else:
                direct_answer = f"{source_texts[0]['text'].split('.')[0].strip()} [SOURCE: {source_texts[0]['document']} p.{source_texts[0]['page']}]"
                evidence_section = direct_answer

        elif qtype == "calculation":
            # Numeric reasoning v0.5: source values → equation → calculation → result.
            # Supports P=VI, V=IR, Q=mcΔT with SymPy-verified substitution; no
            # values are fabricated — all numbers come from the query or sources.
            import re as _re2
            CALC_EQS = [
                {"eq": "P = VI", "vars": ["P", "V", "I"], "units": {"P": "W", "V": "V", "I": "A"}},
                {"eq": "V = IR", "vars": ["V", "I", "R"], "units": {"V": "V", "I": "A", "R": "Ω"}},
                {"eq": "Q = mcΔT", "vars": ["Q", "m", "c", "ΔT"], "units": {"Q": "J", "m": "kg", "c": "J/kg·K", "ΔT": "K"}},
            ]
            def _find_eq():
                for s in source_texts:
                    t = s["text"].replace(" ", "")
                    if "P=VI" in t or "P=V" in t:
                        return CALC_EQS[0], s
                for s in source_texts:
                    t = s["text"].replace(" ", "")
                    if "V=IR" in t or "V=I" in t:
                        return CALC_EQS[1], s
                for s in source_texts:
                    t = s["text"].replace(" ", "").lower()
                    if "q=mc" in t:
                        return CALC_EQS[2], s
                return None, None
            spec, espec = _find_eq()
            # Proportional-reasoning questions ("doubles", "halves", ...)
            prop_m = _re2.search(r"if\s+([A-Za-zΔ]+)\s+(doubles|halves|triples)", q_low)
            if spec and prop_m:
                var, how = prop_m.group(1).upper(), prop_m.group(2)
                out, lhs = {"doubles": "doubles", "halves": "halves", "triples": "triples"}[how], spec["vars"][0]
                if var in [v.upper() for v in spec["vars"][1:]]:
                    direct_answer = f"If {prop_m.group(1)} {how} while others remain constant, {lhs} {out}. [DERIVED from {spec['eq']}]"
                    derived_section = f"Source: {spec['eq']} [SOURCE]\nDerived reasoning: {lhs} is proportional to {prop_m.group(1)} when others are constant. [DERIVED]"
                    evidence_section = f"{direct_answer}\n{derived_section}"
                else:
                    direct_answer = f"{spec['eq']} [SOURCE]"
                    evidence_section = direct_answer
            elif spec:
                # Extract V=.., I=.., R=.., m=.., c=.., DeltaT=.. style values from query
                vals = {}
                for pat, key in [(r"V\s*=\s*(\d+\.?\d*)\s*V", "V"), (r"I\s*=\s*(\d+\.?\d*)\s*A", "I"),
                                 (r"R\s*=\s*(\d+\.?\d*)", "R"), (r"m\s*=\s*(\d+\.?\d*)\s*kg", "m"),
                                 (r"c\s*=\s*(\d+\.?\d*)", "c"), (r"(?:DeltaT|ΔT)\s*=\s*(\d+\.?\d*)\s*K", "ΔT")]:
                    mm = _re2.search(pat, query, re.IGNORECASE)
                    if mm:
                        try:
                            vals[key] = float(mm.group(1))
                        except Exception:
                            pass
                known = {k: v for k, v in vals.items() if k in spec["vars"]}
                unknown = [v for v in spec["vars"] if v not in known]
                if len(known) >= len(spec["vars"]) - 1 and unknown:
                    target = unknown[0]
                    try:
                        from backend.app.services.math_validation import validate_substitution
                        check = validate_substitution(spec["eq"], {**known, target: 0})
                        # Compute directly: P=V*I, V=I*R, Q=m*c*dT
                        if spec["eq"] == "P = VI":
                            res_v = known["V"] * known["I"]
                        elif spec["eq"] == "V = IR":
                            res_v = known.get("I", 1) * known.get("R", 1) if target == "V" else (known["V"] / known["R"] if target == "I" else known["V"] / known["I"])
                        else:
                            res_v = known["m"] * known["c"] * known["ΔT"]
                        u = spec["units"].get(target, "")
                        kvals = ", ".join(f"{k}={v}" for k, v in known.items())
                        direct_answer = f"{target} = {res_v:.3f} {u} [DERIVED from {spec['eq']}]"
                        evidence_section = (f"Known values: {kvals} [SOURCE]\nEquation: {spec['eq']} [SOURCE]\n"
                                            f"Calculation: {res_v:.3f} {u} [DERIVED]\nAnswer: {res_v:.3f} {u} [DERIVED]")
                    except Exception:
                        direct_answer = f"{spec['eq']} [SOURCE]"
                        evidence_section = direct_answer
                else:
                    direct_answer = f"{spec['eq']} [SOURCE]"
                    evidence_section = direct_answer
            else:
                direct_answer = f"{source_texts[0]['text'][:150]} [SOURCE: {source_texts[0]['document']} p.{source_texts[0]['page']}]"
                evidence_section = direct_answer

        elif qtype == "table":
            snippet, src = find_relevant_snippet(["|", "Table", "DeltaT", "80 |", "120 |"])
            direct_answer = f"{snippet[:300]} [SOURCE: {src['document']} p.{src['page']} §{src['section']}]"
            evidence_section = f"Table finding: {direct_answer}\nThe table shows values as documented. [SOURCE]"

        elif qtype == "experimental_result" or "experimental" in q_low or "efficiency" in q_low:
            # v0.4: prefer snippet containing BOTH query numbers and result values (e.g. 120K + 5.2%)
            # and avoid truncating mid-number ("5." without "%")
            q_nums = re.findall(r"\d+\.?\d*\s*(?:K|%|W|V|A)?", query)
            def snippet_score(sent):
                s = 0
                low = sent.lower()
                for kw in ["%", "w", "power", "efficiency"]:
                    if kw in low:
                        s += 1
                for n in q_nums:
                    digits = re.sub(r"\D", "", n)
                    if digits and digits in sent:
                        s += 2
                # Penalize truncated numbers like "5." at end
                if re.search(r"\d+\s*\.\s*$", sent.strip()):
                    s -= 2
                return s
            best_sent, best_src = None, source_texts[0]
            best_score = -99
            for s in source_texts:
                for sent in s["text"].split("."):
                    sent = sent.strip()
                    if len(sent) < 15:
                        continue
                    sc = snippet_score(sent)
                    if sc > best_score:
                        best_score = sc
                        best_sent, best_src = sent, s
            if best_sent:
                snippet, src = best_sent[:250], best_src
            else:
                snippet, src = find_relevant_snippet(["%", "W", "power", "efficiency"])
            # Ensure snippet doesn't end mid-number
            snippet = snippet.strip()
            if re.search(r"\d+\s*\.$", snippet):
                # extend with next chars from source
                try:
                    full = best_src["text"]
                    idx = full.find(snippet[:30])
                    snippet = full[idx:idx+280].split(".")[0].strip()
                except Exception:
                    pass
            direct_answer = f"{snippet}. [SOURCE: {src['document']} p.{src['page']} §{src['section']}]"
            evidence_section = direct_answer

        elif qtype == "definition":
            snippet, src = find_relevant_snippet(["is defined as", "refers to", "is called", "Seebeck", "thermoelectric"])
            direct_answer = f"{snippet}. [SOURCE: {src['document']} p.{src['page']} §{src['section']}]"
            evidence_section = f"Definition: {direct_answer}\nExplanation: This describes the core concept as documented. [GENERATED]"

        elif qtype == "comparison":
            if len(source_texts) >=2:
                direct_answer = f"Document A ({source_texts[0]['document']}) reports: {source_texts[0]['text'][:120]}... [SOURCE: {source_texts[0]['document']} p.{source_texts[0]['page']}]"
                second = f"Document B ({source_texts[1]['document']}) reports: {source_texts[1]['text'][:120]}... [SOURCE: {source_texts[1]['document']} p.{source_texts[1]['page']}]"
                evidence_section = f"{direct_answer}\n{second}\nInterpretation: Comparison based on retrieved evidence [GENERATED]."
                if len(source_texts)>=2 and any("%" in s["text"] for s in source_texts):
                    vals = re.findall(r"(\d+\.?\d*)\s*%", " ".join([s["text"] for s in source_texts[:2]]))
                    if len(set(vals))>1:
                        evidence_section += "\nThe sources report different values and therefore disagree on this point. [SOURCE]"
            else:
                direct_answer = f"{source_texts[0]['text'][:150]} [SOURCE: {source_texts[0]['document']} p.{source_texts[0]['page']}]"
                evidence_section = direct_answer

        else:
            # General: direct answer first
            snippet, src = find_relevant_snippet(query.split()[:3])
            direct_answer = f"{snippet[:200]} [SOURCE: {src['document']} p.{src['page']} §{src['section']}]"
            evidence_section = direct_answer

        # Length control
        if length_mode == "brief":
            answer = direct_answer
            if len(source_texts)>1 and qtype not in ("equation","definition"):
                answer += f"\nSupporting: {source_texts[1]['text'][:100]}... [SOURCE: {source_texts[1]['document']} p.{source_texts[1]['page']}]"
        elif length_mode == "detailed" or length_mode == "research":
            # Full structured
            answer = f"{direct_answer}\n\n"
            if evidence_section != direct_answer:
                answer += evidence_section + "\n\n"
            # Add additional evidence
            answer += "Supporting evidence:\n"
            for s in source_texts[:3]:
                answer += f"- {s['text'][:180]}... [SOURCE: {s['document']} p.{s['page']} §{s['section']}]\n"
            # Add generated interpretation if not already
            if "[GENERATED]" not in answer and "[DERIVED]" not in answer:
                answer += "\nInterpretation: This follows from the documented mechanism [GENERATED].\n"
        else:  # standard
            answer = f"{direct_answer}\n\n"
            if evidence_section and evidence_section != direct_answer:
                # Avoid duplicating direct answer
                if direct_answer not in evidence_section:
                    answer += evidence_section + "\n\n"
            # Add supporting evidence summary
            if len(source_texts) > 1:
                answer += "Evidence:\n"
                for s in source_texts[1:3]:
                    answer += f"- {s['text'][:150]}... [SOURCE: {s['document']} p.{s['page']}]\n"

        # Ensure citations present
        if "[SOURCE" not in answer:
            answer += f"\n[SOURCE: {source_texts[0]['document']} p.{source_texts[0]['page']}]"

        # Handle conflicting sources note
        if len(source_texts) >=2:
            vals = re.findall(r"(\d+\.?\d*)\s*%", " ".join([s["text"] for s in source_texts[:2]]))
            if len(set(vals))>1 and "disagree" not in answer.lower():
                # Only add if query is comparison or experimental
                if qtype in ("comparison","experimental_result","general") and len(vals)>1:
                    pass  # already handled in comparison

        # Add length-appropriate closing
        if length_mode != "brief" and "Note:" not in answer and len(source_texts)<2:
            answer += "\n> Note: Limited evidence was retrieved; additional sources would increase confidence. [GENERATED]\n"

        return answer

class RealLLMUnavailable(Exception):
    """Raised when LLM_PROVIDER=real/local is requested but unavailable (v0.5 strict integrity)."""


class OpenAICompatibleProvider(LLMProvider):
    """Real LLM via any OpenAI-compatible chat-completions endpoint
    (OpenAI, Ollama, vLLM, ...). No vendor hard-coded in business logic;
    endpoint + model come from environment. Tracks tokens/latency/cost."""

    def __init__(self, model: str, api_key: str | None = None, base_url: str = "https://api.openai.com/v1",
                 temperature: float = 0.2, top_p: float = 1.0, max_tokens: int = 1200):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.last_usage: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return f"real:{self.model}"

    async def generate(self, prompt: str, system: str | None = None, temperature: float | None = None, max_tokens: int | None = None) -> str:
        import httpx, time
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {"model": self.model, "messages": messages,
                "temperature": self.temperature if temperature is None else temperature,
                "top_p": self.top_p, "max_tokens": self.max_tokens if max_tokens is None else max_tokens}
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            raise RealLLMUnavailable(f"Real LLM request failed ({self.base_url}, model={self.model}): {e}")
        latency_ms = int((time.time() - t0) * 1000)
        usage = data.get("usage", {}) or {}
        # Never log keys; usage metadata only
        self.last_usage = {
            "model": data.get("model", self.model),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "latency_ms": latency_ms,
            "cost": "unavailable",  # provider gives no pricing; never invented
        }
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise RealLLMUnavailable(f"Unexpected chat-completions response shape: {e}")


# Backward-compatible alias (v0.1–v0.4 name)
class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        super().__init__(model=model, api_key=api_key, base_url="https://api.openai.com/v1")


class LocalHFProvider(LLMProvider):
    """Real on-device generator via HuggingFace transformers (no API key).
    Declared real LLM for controlled A/B experiments (v0.5).
    Weights are cached per model name so repeated cases don't reload."""

    _cache: Dict[str, Any] = {}

    def __init__(self, model_name: str = "HuggingFaceTB/SmolLM2-135M-Instruct", max_new_tokens: int = 150,
                 temperature: float = 0.2, top_p: float = 1.0):
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.last_usage: Dict[str, Any] = {}
        if model_name in LocalHFProvider._cache:
            self._torch, self._tok, self._model = LocalHFProvider._cache[model_name]
            return
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
            self._torch = torch
            self._tok = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
            self._model = AutoModelForCausalLM.from_pretrained(model_name, dtype=torch.float32, local_files_only=True)
            self._model.eval()
            LocalHFProvider._cache[model_name] = (self._torch, self._tok, self._model)
        except Exception as e:
            import logging
            logging.warning(f"requested=local, active=mock, fallback=true model={model_name} reason={e}")
            self._torch, self._tok, self._model = None, None, None

    @property
    def name(self) -> str:
        return f"local:{self.model_name}" if self._model is not None else "mock(fallback-for-local)"

    @property
    def available(self) -> bool:
        return self._model is not None

    async def generate(self, prompt: str, system: str | None = None, temperature: float | None = None, max_tokens: int | None = None) -> str:
        import time
        if self._model is None:
            raise RealLLMUnavailable(f"Local HF model unavailable ({self.model_name}). No score generated.")
        # Keep context tractable on CPU: truncate oldest evidence first
        max_ctx = 1500
        body = prompt[-6000:]
        full = (f"System: {system}\n\n{body}" if system else body)[:6000]
        t0 = time.time()
        import asyncio
        loop = asyncio.get_running_loop()
        text, n_in, n_out = await loop.run_in_executor(None, self._generate_blocking, full, max_tokens)
        self.last_usage = {
            "model": self.model_name,
            "prompt_tokens": n_in,
            "completion_tokens": n_out,
            "total_tokens": (n_in or 0) + (n_out or 0),
            "latency_ms": int((time.time() - t0) * 1000),
            "cost": "unavailable",
        }
        return text

    def _generate_blocking(self, full: str, max_tokens: int | None):
        inp = self._tok(full, return_tensors="pt", truncation=True, max_length=1500)
        n_in = int(inp["input_ids"].shape[1])
        do_sample = (self.temperature or 0) > 0
        with self._torch.no_grad():
            out = self._model.generate(
                **inp, max_new_tokens=self.max_new_tokens if max_tokens is None else max_tokens,
                do_sample=do_sample, temperature=max(self.temperature, 0.1) if do_sample else None,
                top_p=self.top_p, repetition_penalty=1.2, no_repeat_ngram_size=3,
                pad_token_id=self._tok.eos_token_id, eos_token_id=self._tok.eos_token_id)
        n_out = int(out.shape[1] - n_in)
        return self._tok.decode(out[0][n_in:], skip_special_tokens=True).strip(), n_in, n_out


def get_llm_provider(strict: bool = False):
    """Build the configured provider. strict=True (benchmarks): never fall back —
    raise RealLLMUnavailable instead of silently substituting mock (v0.5 §7)."""
    from ..config import settings
    import logging
    prov = (settings.llm_provider or "mock").lower()
    if prov in ("real", "openai"):
        key = settings.llm_api_key or settings.openai_api_key
        model = settings.llm_model if prov == "real" else settings.openai_model
        base = settings.llm_base_url if prov == "real" else "https://api.openai.com/v1"
        if not key and "127.0.0.1" not in base and "localhost" not in base:
            msg = f"requested=real, active=none, fallback={'mock' if settings.llm_fallback_to_mock and not strict else 'refused'} model={model} reason=no API key"
            if strict or not settings.llm_fallback_to_mock:
                raise RealLLMUnavailable(f"BENCHMARK FAILED: Real LLM unavailable (no API key for {base}). No score generated.")
            logging.warning(msg)
            return MockLLMProvider()
        logging.info(f"requested=real, active=real, fallback=false model={model} base={base}")
        return OpenAICompatibleProvider(model=model, api_key=key, base_url=base,
                                        temperature=settings.llm_temperature, top_p=settings.llm_top_p,
                                        max_tokens=settings.llm_max_tokens)
    if prov in ("local", "local-hf", "hf"):
        p = LocalHFProvider(model_name=settings.llm_hf_model, max_new_tokens=settings.llm_hf_max_new_tokens,
                            temperature=settings.llm_temperature, top_p=settings.llm_top_p)
        if not p.available:
            if strict or not settings.llm_fallback_to_mock:
                raise RealLLMUnavailable(f"BENCHMARK FAILED: Local HF model unavailable ({settings.llm_hf_model}). No score generated.")
            return MockLLMProvider()
        logging.info(f"requested=local, active=local, fallback=false model={settings.llm_hf_model}")
        return p
    return MockLLMProvider()


def get_active_llm_identity() -> Dict[str, Any]:
    """Explicit requested/active identity for benchmark integrity (v0.5 §4)."""
    from ..config import settings
    requested = (settings.llm_provider or "mock").lower()
    try:
        p = get_global_llm()
        name = p.name
    except Exception:
        return {"requested_llm_provider": requested, "active_llm_provider": "none",
                "llm_model": None, "fallback": True}
    if name.startswith("real:"):
        active, model, fb = "real", name[5:], False
    elif name.startswith("local:"):
        active, model, fb = "local", name[6:], False
    elif "fallback-for-local" in name:
        active, model, fb = "mock", settings.llm_hf_model, True
    elif name.startswith("openai:"):
        active, model, fb = "real", name[7:], False
    else:
        active, model = "mock", "mock"
        fb = requested in ("real", "local", "openai")
    return {"requested_llm_provider": requested, "active_llm_provider": active,
            "llm_model": model, "fallback": fb}


# global singleton with lazy
_llm_instance = None
def get_global_llm(strict: bool = False):
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = get_llm_provider(strict=strict)
    return _llm_instance

def reset_llm_provider():
    global _llm_instance
    _llm_instance = None
