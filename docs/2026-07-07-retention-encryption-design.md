# Retention & At-Rest Encryption — design (Move 4, D-72)

Status 2026-07-07: **design complete; retention primitives (hold, export, audit log,
honest certificate) SHIPPING now; per-matter encryption + crypto-shred DEFERRED to its
own focused cycle** (rationale in §5 — this is the one Move where "go as far as quality
allows, never past it" bites, and rushing key management on client data is how trust
products die).

## 1. Goal

Retention duties are the demand (Rules 1.15/1.16(d): keep the file ~5-10 years, then
surrender/destroy; OCG "return or destroy with written certification"; FRCP 37(e)
litigation holds). The product answer, in dependency order:

1. **Legal hold** — a first-class object that freezes any disposition of a matter and
   logs itself. No crypto needed. SHIPS NOW.
2. **Export-everything** — one action produces the matter's complete file: original
   natives + chat threads + citations manifest. Surrender BEFORE disposition, always.
   No crypto needed. SHIPS NOW.
3. **Audit log** — hash-chained, append-only, local (RFC 6962-style: each entry hashes
   the previous), covering hold/release/export/disposition events. Tamper-EVIDENT
   without any server. No crypto secrets needed. SHIPS NOW.
4. **Disposition + certificate** — deletes the matter's documents, chunks, line maps,
   threads, and managed copies; runs store compaction so deleted rows leave the live
   LanceDB files; emits a Certificate of Disposition modeled on NIST SP 800-88r2
   App. C. **The certificate states its method HONESTLY: today that method is "Clear"**
   (files unlinked + store compacted on an SSD; snapshots/backups outside app control),
   NOT "Purge". SHIPS NOW with that exact language.
5. **Per-matter encryption -> crypto-shred** — upgrades the disposition method to
   NIST "Purge (cryptographic erase)". DEFERRED (§4-5).

## 2. What ships now (retention.py + routes_retention.py)

- Catalog gains `legal_holds(matter_slug, reason, created, released, released_reason)`
  and `audit_log(id, prev_hash, entry_hash, ts, event, matter_slug, detail)`.
- `place_hold / release_hold / active_hold(matter)`; disposition and document deletion
  REFUSE while a hold is active (409 with the hold reason).
- `export_matter(matter) -> zip` containing: original files (natives, from
  documents/kb/<slug>), `threads.json` (full chat history + citations), `documents.json`
  (catalog rows incl. checksums), `audit.json` (the matter's chain slice).
- `dispose_matter(matter)`: hold check -> export manifest recorded -> delete chunks
  (store delete + optimize/compact) -> delete line maps, threads, documents, managed
  copies (structurally locked to documents/kb/) -> matter row removed -> certificate
  JSON (matter, doc checksums, method="Clear (files unlinked; vector store compacted)",
  caveats=["OS snapshots/backups outside app control", "upgrade to cryptographic erase
  planned"], timestamp, audit-chain head) -> audit entry.
- Audit chain verification: `verify_chain()` recomputes hashes; any edit breaks it.
  Surfaced in Settings.

## 3. Encryption design (for the next cycle)

- **Envelope scheme**: one master key in the macOS Keychain (Secure-Enclave-backed key
  where available, via Security framework through `keyring` or ctypes; NEVER a file);
  per-matter Data Encryption Keys (DEK) wrapped by the master key, stored in the
  catalog. AES-256-GCM.
- **Catalog**: move to SQLCipher (`sqlcipher3` wheel) keyed by the master key. One-time
  migration mirroring reingest_kb's rename-aside pattern.
- **LanceDB**: OSS Lance has no at-rest encryption -> encrypt at the FILE layer: the
  store directory lives inside an encrypted sparse bundle (hdiutil APFS encrypted
  volume keyed by the DEK), mounted at app start, ejected on quit. This avoids forking
  Lance and keeps the query path unchanged. Per-matter granularity = per-matter volumes
  OR (simpler v1) one encrypted volume for the whole KB + per-matter DEK applied to the
  EXPORT/original-copies tree; crypto-shred then requires per-matter volumes — decide
  with a measured prototype (mount latency, concurrent access).
- **Crypto-shred**: destroy the matter's wrapped DEK (catalog row + Keychain sync item)
  -> ciphertext is irrecoverable regardless of snapshots/wear leveling -> certificate
  method upgrades to "Purge (cryptographic erase, NIST SP 800-88r2)".
- **Invariants**: verifier/matter-isolation untouched (encryption is below the store
  API); [GATE] full golden + scale evals after the storage swap; measured latency
  budget: mount+first-query overhead < 500ms.

## 4. Why encryption is deferred, honestly

(a) Key custody mistakes are unrecoverable for real client data — this needs its own
focused cycle with a migration rehearsal and a data-loss drill, not the tail of a
twelve-hour session. (b) The sparse-bundle approach needs a measured prototype before
committing (mount latency, Time Machine interaction, multi-volume ergonomics). (c) The
trust page already states the honest current posture (FileVault + exclusions; encryption
in development) — shipping the retention primitives now delivers attorney value without
overclaiming. The site will not claim encryption until it ships (D-62 ethos).

## 5. Acceptance shipped this cycle

create matter -> ingest -> place hold -> disposition REFUSED (409, reason shown) ->
release hold -> export zip contains natives + threads + manifests -> dispose ->
documents/chunks/line-maps/threads gone, store compacted, matter absent from /matters ->
certificate JSON emitted with method="Clear" + caveats -> audit chain verifies; tamper
with any entry -> verify_chain() fails.
