"""D1 — real-PDF form-robustness techniques reimplemented on PyMuPDF (M6-readiness prep).

Ports three battle-tested techniques from freelawproject/bankruptcy-parser onto PyMuPDF —
NO new dependency (no pdfplumber/PyPDF2). They help extract filled court/agency forms, where
entered data must be separated from pre-printed labels:

1. ``horizontal_rule_lines`` — form rule lines from ``page.get_drawings()`` (line + rect
   edges). (bankruptcy-parser used pdfplumber ``page.lines``; PyMuPDF exposes the geometry.)
2. ``text_above_rule`` — "crop above the rule line": the entered value sits just above a
   form rule; extract the text box above the line (``utils.crop_and_extract``).
3. ``iter_spans`` + ``is_input_span`` — font-size/name span filtering from
   ``page.get_text("dict")`` (bbox+size+font) to separate entered data from pre-printed
   labels (``filters.keys_and_input_text``).
4. ``normalize_checkbox`` — symbol-font (Wingdings) checkbox glyph -> ``[√]`` / ``[ ]``
   (``filters.filter_boxes``: cid:132/checked, cid:134/unchecked).

All read-only; synthetic/public docs only (M6 real data is owner-gated).
"""

import fitz

# Pre-printed label fonts (entered data is a DIFFERENT font); compared case-insensitively,
# after stripping a subset prefix like "WQPAYT+LiberationSans".
LABEL_FONTS = {"arialmt", "arial-italicmt", "liberationsans", "helvetica", "helv"}
INPUT_SIZE_BAND = (8.5, 9.1)  # entered-data size band (bankruptcy-parser forms)

# Common Wingdings checkbox glyphs (PyMuPDF returns the char or a cid token).
_CHECKED = {"ü", "ý", "þ", "n", "", "", "", "cid:132", "cid:0xfc"}
_UNCHECKED = {"o", "q", "¨", "", "", "cid:134", "cid:0xa8"}


def horizontal_rule_lines(page, min_len=40, tol=1.5):
    """Horizontal rule lines on ``page`` as ``[{x0, x1, y}]`` (left→right), from vector
    drawings — both explicit line segments and the top/bottom edges of thin rectangles."""
    lines = []
    for d in page.get_drawings():
        for item in d.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) <= tol and abs(p2.x - p1.x) >= min_len:
                    x0, x1 = sorted((p1.x, p2.x))
                    lines.append({"x0": x0, "x1": x1, "y": (p1.y + p2.y) / 2})
            elif item[0] == "re":
                r = item[1]
                if r.width >= min_len and r.height <= tol:  # a thin rect == a rule
                    lines.append({"x0": r.x0, "x1": r.x1, "y": (r.y0 + r.y1) / 2})
    return lines


def text_above_rule(page, line, up_shift=20, left_shift=0):
    """Entered text in the box directly ABOVE a rule line (the value written on the line)."""
    clip = fitz.Rect(line["x0"] - left_shift, line["y"] - up_shift, line["x1"], line["y"])
    return page.get_text("text", clip=clip).strip()


def iter_spans(page):
    """Yield ``{text, font, size, bbox}`` for every text span (get_text 'dict')."""
    for block in page.get_text("dict").get("blocks", []):
        for ln in block.get("lines", []):
            for sp in ln.get("spans", []):
                yield {"text": sp["text"], "font": sp["font"],
                       "size": round(sp["size"], 2), "bbox": tuple(sp["bbox"])}


def _bare_font(font):
    return font.lower().split("+")[-1]


def is_input_span(span, size_band=INPUT_SIZE_BAND, label_fonts=LABEL_FONTS):
    """True if ``span`` looks like ENTERED data, not a pre-printed label: its size is within
    the input band AND its font is not a known label font (bankruptcy-parser
    keys_and_input_text)."""
    fn = _bare_font(span["font"])
    in_band = size_band[0] < span["size"] < size_band[1]
    is_label_font = any(lf in fn for lf in label_fonts)
    return bool(in_band and not is_label_font)


def normalize_checkbox(font, char):
    """Map a symbol-font (Wingdings) checkbox glyph to ``"[√]"`` (checked) / ``"[ ]"``
    (unchecked), or ``None`` if it isn't a recognized checkbox glyph."""
    if "wingding" not in font.lower():
        return None
    c = (char or "").strip()
    if c in _CHECKED:
        return "[√]"
    if c in _UNCHECKED:
        return "[ ]"
    return None


def extract_form_fields(page, up_shift=20):
    """Convenience: the entered value above each rule line on ``page`` (non-empty only)."""
    out = []
    for line in horizontal_rule_lines(page):
        val = text_above_rule(page, line, up_shift=up_shift)
        if val:
            out.append({"line_y": round(line["y"], 1), "value": val})
    return out
