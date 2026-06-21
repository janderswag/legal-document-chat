"""M2-5 — Hand-rolled grounded answering over the matter-filtered context.

A thin, transparent function (no LlamaIndex, D-37): take the matter-filtered
top-k chunks from M2-4 (rerank=False base path), assemble a context block with
explicit per-chunk source labels we control, apply the CE_PLAN §10 grounded-answer
+ refusal prompt, call qwen3:14b on the loopback Ollama, strip any <think> block,
and return a structured result. The grounding_chunks (with char offsets) are the
substrate the M2-6 mechanical span check will verify; the model's asserted
citations are parsed back to chunk_ids where possible.

Scope (M2-5): answering only. No mechanical span verification (M2-6 — but the
offsets it needs ARE returned here), no reranker (rerank=False), no LlamaIndex
(D-37), no HTTP surface (M2-7).
"""

import html
import json
import math
import re
import time
import urllib.request

from embed_store import ollama_url
from retrieval import retrieve

REFUSAL = "I could not find this in the documents."

# CE_PLAN §10 default system prompt (grounded-answer rules + the exact refusal
# sentence + verbatim-citation format). The <context>/question go in the user turn.
SYSTEM_PROMPT = """You are a private document assistant for an attorney. You help locate, summarize,
and quote information from the attorney's own documents. You are NOT a lawyer and
you do NOT give legal advice, legal opinions, predictions, or strategy.

RULES — follow exactly:

1. Answer ONLY using the provided <context> chunks. Do not use outside knowledge.
   If the answer is not in the context, respond exactly:
   "I could not find this in the documents."

2. Cite every factual statement. After each claim, include a citation in the form:
   [document: <original_filename>, page: <page_number>, section: <section_heading>,
    chunk: <chunk_id>, span: "<exact quoted text you relied on>"]
   The span MUST be copied verbatim from the provided context. Only cite documents,
   pages, sections, and chunk ids that appear in the provided context. Never invent or
   guess a citation, page number, document name, or span.

3. When the user asks what a document says, prefer a direct verbatim quote from the
   context, in quotation marks, followed by its citation.

4. If the context only partially supports an answer, say what is supported, cite it,
   and clearly state what is missing. Do not fill gaps with assumptions.

5. Do not give legal advice or legal conclusions. You may summarize and locate what
   the documents say; you may not advise on what the attorney should do.

6. End every response with this reminder:
   "Verify against the cited source. This is not legal advice."

You have no access to the internet, email, file changes, or any external tools.
Your only inputs are the user's question and the provided document context."""

_CITE_RE = re.compile(
    r"\[\s*document:\s*(?P<doc>[^,\]]+?)\s*,\s*page:\s*(?P<page>\d+)(?P<rest>[^\]]*)\]",
    re.IGNORECASE | re.DOTALL,
)
_CHUNK_RE = re.compile(r"chunk:\s*(C\d+)", re.IGNORECASE)
_SPAN_RE = re.compile(r"span:\s*\"?(.+?)\"?\s*$", re.IGNORECASE | re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_BRACKET_RE = re.compile(r"\[([^\]]+)\]")
_QUOTED_RE = re.compile(r"\"([^\"]{15,})\"")


def _norm(text):
    """Quote/whitespace-insensitive form for mapping a quoted span back to a chunk.

    Aligned with the verifier's normalization contract (B1): decode HTML entities and drop
    backslashes that escape a quote BEFORE the reflow/quote/case pass, so a tag-less escaped
    span (``&quot;``, ``\\"``) resolves to its chunk instead of false-rejecting. Precision
    only — it just removes characters, so it can recover a truthful span but never make a
    fabricated one match (the mechanical verifier remains the separate display gate)."""
    text = html.unescape(text)
    text = re.sub(r'\\(?=["\'“”‘’])', "", text)  # drop a backslash escaping a quote
    text = re.sub(r"-\n", "-", text)
    text = re.sub(r"[\"'“”‘’]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _post_chat(messages, host=None, model="qwen3:14b", want_logprobs=False):
    """Loopback Ollama /api/chat call -> the full response dict. When ``want_logprobs`` is
    set, requests per-token logprobs (for the B4 confidence signal); otherwise the request
    body is identical to the original _chat call (parity preserved)."""
    host = host or ollama_url()
    payload = {"model": model, "stream": False, "think": False,
               "messages": messages, "options": {"temperature": 0}}
    if want_logprobs:
        payload["logprobs"] = True
    req = urllib.request.Request(
        f"{host}/api/chat", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def _chat(messages, host=None, model="qwen3:14b"):
    return _post_chat(messages, host=host, model=model)["message"]["content"]


def confidence_from_logprobs(logprobs):
    """Non-gating answer confidence = exp(mean token logprob) (kotaemon qa_score), in
    (0, 1], or None when no logprobs are present. DISPLAY ONLY — never feeds the verifier,
    so it cannot change which citations are verified/displayed (D-19/D-38)."""
    vals = [x["logprob"] for x in (logprobs or [])
            if isinstance(x, dict) and isinstance(x.get("logprob"), (int, float))]
    if not vals:
        return None
    return math.exp(sum(vals) / len(vals))


def _chat_stream_ttft(messages, host=None, model="qwen3:14b", think=False,
                      num_predict=None, keep_alive=None):
    """Streaming variant used ONLY by the latency harness (G-LAT) — a side channel that
    does NOT touch answer()/_chat (M2-7 parity). Streams the Ollama response and stamps
    the wall-clock from request-send to the FIRST non-empty content token (TTFT).

    Returns (text, ttft_s, total_s). Loopback Ollama only. Knobs: think=False (qwen3
    no-think), bounded num_predict, warm keep_alive — documented latency levers."""
    host = host or ollama_url()
    body = {"model": model, "stream": True, "think": think,
            "messages": messages, "options": {"temperature": 0}}
    if num_predict is not None:
        body["options"]["num_predict"] = num_predict
    if keep_alive is not None:
        body["keep_alive"] = keep_alive
    req = urllib.request.Request(
        f"{host}/api/chat", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    ttft, parts = None, []
    with urllib.request.urlopen(req) as resp:
        for line in resp:
            if not line.strip():
                continue
            obj = json.loads(line)
            chunk = obj.get("message", {}).get("content", "")
            if chunk:
                if ttft is None:
                    ttft = time.perf_counter() - t0
                parts.append(chunk)
            if obj.get("done"):
                break
    total = time.perf_counter() - t0
    return "".join(parts), (ttft if ttft is not None else total), total


def _extract_and_resolve(answer_text, grounding):
    """Extract the model's asserted claims and resolve each to a grounding chunk.

    A claim = {span, chunk_hint, target}. The model's prose (a §10 tag and/or a
    quoted span) is only a POINTER: resolution prefers the asserted chunk_id (so a
    wrong pointer is later checked against the wrong chunk and rejected), else maps
    the quoted span to the chunk that contains it. ``target`` is the resolved
    grounding chunk (or None). filename/page are NEVER read from the model — callers
    derive them from ``target`` (D-38).
    """
    by_id = {g["chunk_id"]: g for g in grounding}
    norm_chunks = [(g, _norm(g["text"])) for g in grounding]
    claims, seen = [], set()

    def add_claim(span, chunk_hint):
        span = (span or "").strip().strip('"')
        key = (_norm(span), chunk_hint)
        if key in seen:
            return
        seen.add(key)
        target = by_id.get(chunk_hint)
        if target is None and len(_norm(span)) >= 15:
            for g, ntext in norm_chunks:
                if _norm(span) in ntext:
                    target = g
                    break
        claims.append({"span": span, "chunk_hint": chunk_hint, "target": target})

    # (1) Each [...] bracket is either a citation tag (has document:/page:/chunk:/
    # span:) — parse its span + chunk pointer together so a wrong pointer stays
    # attached and is later rejected — or a plain bracketed verbatim quote.
    for b in _BRACKET_RE.findall(answer_text):
        if any(k in b.lower() for k in ("document:", "page:", "chunk:", "span:")):
            cm = _CHUNK_RE.search(b)
            sm = _SPAN_RE.search(b)
            add_claim(sm.group(1) if sm else "", cm.group(1).upper() if cm else None)
        else:
            add_claim(b, None)

    # (2) Double-quoted spans OUTSIDE any bracket (qwen3's looser, tag-less format).
    for cand in _QUOTED_RE.findall(_BRACKET_RE.sub(" ", answer_text)):
        add_claim(cand, None)
    return claims


def _parse_citations(answer_text, grounding):
    """Resolved, CHUNK-DERIVED citations (D-38): filename+page come from the matched
    chunk's metadata, never the model's asserted page. The model's prose only points
    to a chunk. (Mechanical span-overlap verification + rejection is M2-6/verifier.)
    """
    seen, citations = set(), []
    for cl in _extract_and_resolve(answer_text, grounding):
        g = cl["target"]
        if g is None:
            continue
        key = (g["source_filename"], g["page_number"], g["chunk_id"])
        if key in seen:
            continue
        seen.add(key)
        citations.append({
            "filename": g["source_filename"],
            "page": g["page_number"],
            "chunk_id": g["chunk_id"],
            "span": cl["span"],
        })
    return citations


def _assemble_context(question, matter, top_k, db_path):
    """Retrieve the matter-filtered chunks and build (messages, grounding). Shared by
    answer() and answer_stream() so the prompt + grounding are identical on both paths."""
    chunks = retrieve(question, matter=matter, top_k=top_k, db_path=db_path, rerank=False)
    grounding, context_blocks = [], []
    for i, c in enumerate(chunks, 1):
        cid = f"C{i}"
        grounding.append({
            "chunk_id": cid,
            "source_filename": c["source_filename"],
            "page_number": c["page_number"],
            "char_start": c["char_start"],
            "char_end": c["char_end"],
            "text": c["text"],
        })
        context_blocks.append(
            f"[chunk: {cid} | document: {c['source_filename']} | page: {c['page_number']} "
            f"| section: {c['section']}]\n{c['text']}"
        )
    user = (
        "<context>\n" + "\n\n".join(context_blocks) + "\n</context>\n\n"
        "Cite each factual claim with the tag [document: <filename>, page: <page_number>, "
        "chunk: <chunk_id>, span: \"<verbatim quote>\"] using the chunk labels shown above.\n\n"
        "User question:\n" + question
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    return messages, grounding


def _stream_tokens(messages, host=None, model="qwen3:14b"):
    """Yield qwen3 content deltas from the loopback Ollama stream (think disabled). Used by
    the streaming chat path (B6) for perceived latency — the verifier still runs on the
    fully-assembled text, never on a partial."""
    host = host or ollama_url()
    body = {"model": model, "stream": True, "think": False,
            "messages": messages, "options": {"temperature": 0}}
    req = urllib.request.Request(
        f"{host}/api/chat", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        for line in resp:
            if not line.strip():
                continue
            obj = json.loads(line)
            chunk = obj.get("message", {}).get("content", "")
            if chunk:
                yield chunk
            if obj.get("done"):
                break


def answer(question, matter=None, top_k=5, db_path=None, with_confidence=False):
    """Answer ``question`` grounded in the matter-filtered context; refuse if unsupported.

    Returns {answer_text, citations:[{filename,page,chunk_id}],
    grounding_chunks:[{chunk_id,source_filename,page_number,char_start,char_end,text}]}.

    with_confidence=False (default) is byte-identical to the original behavior — no logprobs
    requested. with_confidence=True adds a display-only ``confidence`` (B4) computed from the
    response logprobs; it never touches the verifier, so citations are unchanged.
    """
    messages, grounding = _assemble_context(question, matter, top_k, db_path)
    confidence = None
    if with_confidence:
        resp = _post_chat(messages, want_logprobs=True)
        raw = resp["message"]["content"]
        confidence = confidence_from_logprobs(resp.get("logprobs"))
    else:
        raw = _chat(messages)
    answer_text = _THINK_RE.sub("", raw).strip()

    # M2-6: mechanically verify each asserted span overlaps its cited chunk's offsets.
    # Verified citations are chunk-derived (D-38); unverifiable claims are surfaced.
    # NOTE: confidence is NOT consulted here — verification is purely mechanical.
    from verifier import verify_answer  # lazy: avoids an import cycle
    verdict = verify_answer(answer_text, grounding)
    result = {
        "answer_text": answer_text,
        "citations": verdict["citations"],
        "rejected_claims": verdict["rejected_claims"],
        "grounding_chunks": grounding,
    }
    if with_confidence:
        result["confidence"] = confidence  # display-only (B4)
    return result


def answer_stream(question, matter=None, top_k=5, db_path=None):
    """Generator for the streaming chat path (B6). Yields ``{"type":"token","text":...}``
    deltas as the model generates, then a final ``{"type":"result", ...}`` whose citations
    come from running the EXACT verifier on the COMPLETE text (never a partial) — so
    streaming changes perceived latency only and preserves never-false-accept (D-19/D-38)."""
    messages, grounding = _assemble_context(question, matter, top_k, db_path)
    parts = []
    for tok in _stream_tokens(messages):
        parts.append(tok)
        yield {"type": "token", "text": tok}
    answer_text = _THINK_RE.sub("", "".join(parts)).strip()
    from verifier import verify_answer  # lazy: avoids an import cycle
    verdict = verify_answer(answer_text, grounding)
    yield {
        "type": "result",
        "answer_text": answer_text,
        "citations": verdict["citations"],
        "rejected_claims": verdict["rejected_claims"],
        "grounding_chunks": grounding,
    }
