"""M2-4 — Metadata-filter-before-similarity retrieval with an explicit matter param.

Matter-scoping is supplied as an explicit ``matter`` filter (D-35) — never inferred
from the question. When a matter is given, LanceDB hard-pre-filters rows to that
matter BEFORE similarity (``prefilter=True``), so the M1 "right clause, wrong
client" cross-matter pull cannot happen; when ``matter is None`` it is an explicit
search-all. The matter value is validated against the store's known matters (an
allowlist) before it touches the filter string, so raw text is never interpolated.

Scope (M2-4): retrieval only. No reranker (M2-4b), answering LLM (M2-5), span
verification (M2-6), or HTTP surface (M2-7).
"""

from pathlib import Path

from embed_store import embed_texts, open_table

_DEFAULT_DB = Path(__file__).resolve().parent / ".lancedb"
_PAYLOAD_FIELDS = (
    "source_filename", "matter", "page_number", "section", "char_start", "char_end", "text",
)
_RRF_K = 60  # Reciprocal Rank Fusion constant (standard default)


# Matter-allowlist cache: db key -> (table_version, frozenset of matter values). Any
# LanceDB write bumps the table version, so a version mismatch invalidates the entry —
# no explicit invalidation hooks needed in the ingest path.
_MATTERS_CACHE = {}


def _store_matters(table, cache_key):
    """Distinct matter values present in the store (the matter allowlist), via a
    matter-COLUMN-ONLY scan cached by table version.

    The previous implementation ran ``table.to_arrow().to_pylist()`` — materializing the
    ENTIRE store (vectors + text) into Python on every matter-scoped query. Measured
    (D-66 scale audit): 1.5s at 10k chunks, 15.6s + 4.7GB RSS at 100k, projected swap
    death at 500k — the app was unusable at ~90 documents. The column scan is O(rows) on
    one short string column (measured ~10ms @100k, ~49ms @500k) and O(1) when the cached
    version matches. Validation SEMANTICS are unchanged: the allowlist is exactly the
    set of matters present in this store (works for eval and KB stores alike; the D-18
    ``prefilter=True`` isolation downstream is untouched)."""
    version = table.version
    hit = _MATTERS_CACHE.get(cache_key)
    if hit and hit[0] == version:
        return hit[1]
    n = table.count_rows()
    col = table.search().select(["matter"]).limit(max(n, 1)).to_arrow()
    matters = frozenset(col["matter"].to_pylist()) if n else frozenset()
    _MATTERS_CACHE[cache_key] = (version, matters)
    return matters


def known_matters(db_path=None):
    """Distinct matter values present in the store (the matter allowlist)."""
    key = str(db_path or _DEFAULT_DB)
    return sorted(_store_matters(open_table(key), key))


def _matter_filter(table, matter, cache_key):
    """Validate ``matter`` against the store allowlist and return a safe filter string
    (or None for search-all). Never interpolates raw user text."""
    if matter is None:
        return None
    if matter not in _store_matters(table, cache_key):
        raise ValueError(f"unknown matter (not in store): {matter!r}")
    return f"matter = '{matter.replace(chr(39), chr(39) * 2)}'"


def _ensure_fts_index(table):
    """Ensure a NATIVE LanceDB full-text (BM25/inverted) index exists on ``text``.
    Built lazily on first hybrid use, then reused. (LanceDB 0.33 removed tantivy-based
    FTS upstream; this uses the built-in native FTS — no tantivy dependency.)"""
    try:
        table.search("probe", query_type="fts").limit(1).to_arrow()
    except Exception:
        table.create_fts_index("text", replace=True)


def _rrf_fuse(dense_rows, fts_rows, top_k, k=_RRF_K):
    """Reciprocal Rank Fusion of two ranked candidate lists, keyed by chunk identity."""
    def key(r):
        return (r["source_filename"], r["page_number"], r["char_start"], r["char_end"])

    scores, payload = {}, {}
    for ranked in (dense_rows, fts_rows):
        for rank, r in enumerate(ranked):
            kk = key(r)
            scores[kk] = scores.get(kk, 0.0) + 1.0 / (k + rank)
            payload.setdefault(kk, r)
    order = sorted(scores, key=lambda kk: scores[kk], reverse=True)
    return [payload[kk] for kk in order[:top_k]]


def retrieve(question, matter=None, top_k=5, db_path=None, rerank=False, candidate_k=20,
             hybrid=False):
    """Return the top-k chunks for ``question``, optionally hard-scoped to ``matter``.

    matter is None -> explicit search-all. matter set -> validated against the
    store's known matters, then a hard pre-filter applied before similarity.

    hybrid=True (M3, G-HYB): fuse dense vector search with native BM25 full-text search
    via Reciprocal Rank Fusion. The matter pre-filter (D-18) is applied to BOTH arms
    BEFORE fusion, so hybrid never reintroduces a cross-matter chunk. hybrid=False is
    the unchanged dense path. (hybrid and rerank are independent; hybrid takes the
    fused result.)

    rerank=True (M2-4b): pull ``candidate_k`` matter-pre-filtered candidates, reorder
    them with the local bge-reranker-v2-m3 cross-encoder, and return the top-k. The
    reranker only reorders the already-filtered set — it never reintroduces another
    matter (the D-18 hard pre-filter is upstream and intact).
    """
    key = str(db_path or _DEFAULT_DB)
    table = open_table(key)
    filt = _matter_filter(table, matter, key)

    def _scoped(search):
        return search.where(filt, prefilter=True) if filt else search

    if hybrid:
        query_vec = embed_texts([question])[0]
        dense = _scoped(table.search(query_vec)).limit(candidate_k).to_arrow().to_pylist()
        _ensure_fts_index(table)
        fts = _scoped(table.search(question, query_type="fts")).limit(candidate_k).to_arrow().to_pylist()
        fused = _rrf_fuse(dense, fts, top_k)
        return [{k: r[k] for k in _PAYLOAD_FIELDS if k in r} for r in fused]

    query_vec = embed_texts([question])[0]
    search = _scoped(table.search(query_vec))
    limit = max(top_k, candidate_k) if rerank else top_k
    rows = search.limit(limit).to_arrow().to_pylist()
    candidates = [{k: r[k] for k in (*_PAYLOAD_FIELDS, "_distance") if k in r} for r in rows]

    if rerank:
        from reranker import rerank as _rerank  # lazy: keep the base path torch-free
        return _rerank(question, candidates, top_k=top_k)
    return candidates[:top_k]
