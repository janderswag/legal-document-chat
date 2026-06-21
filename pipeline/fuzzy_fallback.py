"""B5 — NON-GATING fuzzy span fallback (D-51 push-back; D-19/D-38 preserved).

When the mechanical verifier (verifier.py) finds no exact normalized overlap for an asserted
span, this module may offer a "probable source (unverified)" hint — a difflib near-match to
help the attorney locate where the model was pointing. It is STRICTLY NON-GATING:

- It NEVER returns a citation and NEVER mutates the verified set.
- Every hint is flagged ``verified: False`` and deliberately lacks the verified-citation
  shape (no char offsets, no chunk_id) so it can't be mistaken for one.
- It only considers spans the exact verifier did NOT verify (it skips real citations).

A SequenceMatcher ratio is a similarity score, not a verbatim match — surfacing it as a
verified citation would break our never-false-accept moat. This is a labeled UI aid only.
"""

import difflib
import re

FUZZY_THRESHOLD = 0.82   # SequenceMatcher ratio to surface a probable hint
_MIN_SPAN = 8            # spans shorter than this are too weak to fuzzy-match


def _norm(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _best_window_ratio(span_norm, text_norm):
    """Best SequenceMatcher ratio of ``span_norm`` against any same-length-ish window of
    ``text_norm``. Returns (ratio, matched_substring)."""
    n = len(span_norm)
    if n == 0 or not text_norm:
        return 0.0, ""
    best_r, best_s = 0.0, ""
    # windows of ~span length (a small slack handles minor length drift)
    step = max(1, n // 8)
    for start in range(0, max(1, len(text_norm) - n + 1), step):
        window = text_norm[start:start + n + 4]
        r = difflib.SequenceMatcher(None, span_norm, window).ratio()
        if r > best_r:
            best_r, best_s = r, window
    # also score the whole text (covers a span shorter than the chunk's structure)
    r_full = difflib.SequenceMatcher(None, span_norm, text_norm).quick_ratio()
    if r_full > best_r and len(text_norm) <= n + 8:
        best_r, best_s = r_full, text_norm
    return best_r, best_s


def probable_sources(answer_text, grounding_chunks, threshold=FUZZY_THRESHOLD):
    """Return NON-GATING ``{filename, page, ratio, probable_text, asserted_span,
    verified: False}`` hints for asserted spans the exact verifier could not verify. Empty
    on a refusal. These are UI aids only — never citations, never verified."""
    from answering import REFUSAL, _extract_and_resolve
    from verifier import locate_span

    if REFUSAL in answer_text:
        return []

    hints = []
    for cl in _extract_and_resolve(answer_text, grounding_chunks):
        span = (cl["span"] or "").strip()
        if len(span) < _MIN_SPAN:
            continue
        # skip spans that the EXACT verifier already verifies (those are real citations)
        target = cl["target"]
        if target is not None and locate_span(target["text"], span) is not None:
            continue
        span_norm = _norm(span)
        best = None
        for g in grounding_chunks:
            ratio, where = _best_window_ratio(span_norm, _norm(g["text"]))
            if ratio >= threshold and (best is None or ratio > best["ratio"]):
                best = {"filename": g["source_filename"], "page": g["page_number"],
                        "ratio": round(ratio, 3), "probable_text": where,
                        "asserted_span": span, "verified": False}
        if best:
            hints.append(best)
    return hints
