"""Encryption-cycle prototype (design doc §3, measured-first) — encrypted APFS
sparse bundle hosting a LanceDB store: does mount + first-query overhead fit the
< 500ms budget, and what does per-matter (multi-volume) granularity cost?

Measures, per round (fresh attach each time so the volume cache is cold):
  - hdiutil attach latency (passphrase unlock + APFS mount)
  - first query on the encrypted store (connect + open_table + matter-prefiltered
    vector search, the production retrieve() shape with a fixed synthetic vector —
    no Ollama, so the number is pure storage overhead)
  - the same first query on an unencrypted copy (baseline; warm page cache after
    round 1 — reported per-round so the cold/warm split is visible)
  - hdiutil detach latency
Plus one-time: bundle create + store copy time, per-matter extrapolation (attach
of N small volumes, sequential), and Time Machine interaction (tmutil
addexclusion/isexcluded on the bundle — sticky exclusion is the D-71 pattern).

Read-only with respect to real stores: works on COPIES of pipeline/.lancedb_scale
under a git-ignored scratch dir. Passphrase is a throwaway secrets token held in
memory only (synthetic data; the real design keys volumes from Keychain-wrapped
DEKs, never a literal). Writes eval/results/encvol-proto-<date>.json (git-ignored).

Usage: pipeline/.venv/bin/python pipeline/bench_encrypted_volume.py [rounds]
"""

import json
import secrets
import shutil
import statistics
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import lancedb

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
SOURCE_STORE = PIPELINE_DIR / ".lancedb_scale"  # largest store we have (realism)
SCRATCH = PIPELINE_DIR / ".encvol_proto"
RESULTS_DIR = REPO_ROOT / "eval" / "results"
BUDGET_MS = 500
N_MATTER_VOLUMES = 5  # per-matter extrapolation sample

# The production retrieve() shape: matter prefilter + dense top-5 (D-69 defaults).
QUERY_MATTER = None  # set after we read the store's matters
TOP_K = 5
EMBED_DIM = 1024


def _run(cmd, input_text=None, check=True):
    r = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {r.stderr.strip()}")
    return r


def _timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return (time.perf_counter() - t0) * 1000.0, out


def _fixed_vector():
    """Deterministic 1024-dim query vector (no Ollama dependency)."""
    import random
    rng = random.Random(42)
    return [rng.uniform(-1, 1) for _ in range(EMBED_DIM)]


def _first_query(db_path, matter, vec):
    """Cold connect + open + matter-prefiltered dense search — production shape."""
    db = lancedb.connect(str(db_path))
    table = db.open_table("chunks")
    search = table.search(vec)
    if matter:
        search = search.where(f"matter = '{matter}'", prefilter=True)
    rows = search.limit(TOP_K).to_arrow().to_pylist()
    return rows


def create_bundle(bundle, size, passphrase, volname):
    _run([
        "hdiutil", "create", "-type", "SPARSEBUNDLE", "-fs", "APFS",
        "-encryption", "AES-256", "-stdinpass", "-size", size,
        "-volname", volname, str(bundle),
    ], input_text=passphrase)


def attach(bundle, mountpoint, passphrase):
    _run([
        "hdiutil", "attach", str(bundle), "-stdinpass", "-nobrowse",
        "-mountpoint", str(mountpoint),
    ], input_text=passphrase)


def detach(mountpoint):
    _run(["hdiutil", "detach", str(mountpoint)])


def main(rounds=5):
    if not SOURCE_STORE.exists():
        sys.exit(f"source store missing: {SOURCE_STORE} (run build_scale_store.py)")
    if SCRATCH.exists():
        # a prior crashed run can leave volumes mounted under SCRATCH — detach first
        for m in SCRATCH.glob("mnt*"):
            _run(["hdiutil", "detach", str(m), "-force"], check=False)
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    passphrase = secrets.token_urlsafe(32)
    vec = _fixed_vector()
    report = {"date": date.today().isoformat(), "source_store": str(SOURCE_STORE),
              "store_bytes": sum(f.stat().st_size for f in SOURCE_STORE.rglob("*") if f.is_file()),
              "budget_ms": BUDGET_MS, "rounds": rounds}

    # --- plain baseline copy (outside any volume) ---
    plain_copy = SCRATCH / "plain_store"
    ms, _ = _timed(lambda: shutil.copytree(SOURCE_STORE, plain_copy))
    report["plain_copy_ms"] = round(ms, 1)

    # pick a real matter with >= TOP_K chunks for the prefilter (production always
    # filters by matter; a tiny matter would return short and skew the timing)
    t = lancedb.connect(str(plain_copy)).open_table("chunks")
    from collections import Counter
    counts = Counter(r["matter"] for r in
                     t.search().select(["matter"]).limit(200_000).to_arrow().to_pylist())
    matter = next(m for m, n in counts.most_common() if n >= TOP_K)
    report["query_matter"] = matter

    # --- single-volume bundle: create + populate ---
    bundle = SCRATCH / "kb.sparsebundle"
    mnt = SCRATCH / "mnt"
    ms, _ = _timed(lambda: create_bundle(bundle, "2g", passphrase, "docuchat-kb"))
    report["create_bundle_ms"] = round(ms, 1)
    attach(bundle, mnt, passphrase)
    ms, _ = _timed(lambda: shutil.copytree(SOURCE_STORE, mnt / "store"))
    report["populate_copy_ms"] = round(ms, 1)
    detach(mnt)

    # --- measured rounds: attach -> first query (enc) -> detach; plain first query ---
    per_round = []
    for i in range(rounds):
        attach_ms, _ = _timed(lambda: attach(bundle, mnt, passphrase))
        q_enc_ms, rows = _timed(lambda: _first_query(mnt / "store", matter, vec))
        assert len(rows) == TOP_K, f"expected {TOP_K} rows, got {len(rows)}"
        detach_ms, _ = _timed(lambda: detach(mnt))
        q_plain_ms, rows_p = _timed(lambda: _first_query(plain_copy, matter, vec))
        assert len(rows_p) == TOP_K
        per_round.append({"attach_ms": round(attach_ms, 1),
                          "first_query_enc_ms": round(q_enc_ms, 1),
                          "first_query_plain_ms": round(q_plain_ms, 1),
                          "detach_ms": round(detach_ms, 1),
                          "mount_plus_query_ms": round(attach_ms + q_enc_ms, 1)})
    report["rounds_detail"] = per_round

    def stats(key):
        vals = [r[key] for r in per_round]
        return {"median": round(statistics.median(vals), 1),
                "mean": round(statistics.mean(vals), 1),
                "max": round(max(vals), 1)}

    report["summary"] = {k: stats(k) for k in
                         ("attach_ms", "first_query_enc_ms", "first_query_plain_ms",
                          "detach_ms", "mount_plus_query_ms")}
    # Overhead vs budget: mount + (enc first query - plain first query), median.
    med = report["summary"]
    overhead = med["attach_ms"]["median"] + max(
        0.0, med["first_query_enc_ms"]["median"] - med["first_query_plain_ms"]["median"])
    report["overhead_ms_median"] = round(overhead, 1)
    report["within_budget"] = overhead < BUDGET_MS

    # --- per-matter extrapolation: N small volumes, sequential attach ---
    matter_attach = []
    for i in range(N_MATTER_VOLUMES):
        b = SCRATCH / f"matter{i}.sparsebundle"
        m = SCRATCH / f"mnt_m{i}"
        create_bundle(b, "512m", passphrase, f"docuchat-m{i}")
        ms, _ = _timed(lambda: attach(b, m, passphrase))
        matter_attach.append(round(ms, 1))
        detach(m)
    report["per_matter_attach_ms"] = matter_attach
    report["per_matter_attach_median"] = round(statistics.median(matter_attach), 1)

    # --- Time Machine interaction (D-71 pattern: sticky path exclusion) ---
    tm = {}
    r = _run(["tmutil", "addexclusion", str(bundle)], check=False)
    tm["addexclusion_rc"] = r.returncode
    r = _run(["tmutil", "isexcluded", str(bundle)], check=False)
    tm["isexcluded"] = r.stdout.strip()
    report["time_machine"] = tm

    out = RESULTS_DIR / f"encvol-proto-{report['date']}.json"
    out.write_text(json.dumps(report, indent=2))

    # cleanup: volumes detached above; remove scratch (bundle, copies)
    shutil.rmtree(SCRATCH)

    print(json.dumps(report["summary"], indent=2))
    print(f"overhead (median attach + enc-vs-plain query delta): {overhead:.1f}ms "
          f"-> {'WITHIN' if report['within_budget'] else 'EXCEEDS'} {BUDGET_MS}ms budget")
    print(f"per-matter attach median: {report['per_matter_attach_median']}ms x N matters at app start")
    print(f"time machine: {tm}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
