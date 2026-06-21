# Deploy — scripted redeploy + restore (SC-7)

> ## ⚠️ COMPOSE-ONLY — never `docker run -p` (D-43a, hard rule #4)
> The image's container CMD binds `0.0.0.0` **inside the container only**. The loopback
> boundary is supplied **exclusively** by `docker-compose.yml`, which publishes
> `127.0.0.1:8000:8000`. A bare **`docker run -p 8000:8000 <image>`** would publish to
> `0.0.0.0` and expose the service off-host — a hard-rule violation. **Always** bring the
> service up with `deploy/up.sh` / `docker compose up`. Never `docker run -p` this image.

Compose-only, loopback-only redeploy of the Legal Document Intelligence FastAPI service.
**Never** binds `0.0.0.0`; **never** sets `OLLAMA_HOST`. The published port is bound to
`127.0.0.1` by `docker-compose.yml` (`127.0.0.1:8000:8000`); host Ollama stays on
`127.0.0.1:11434` and is reached from the container via `host.docker.internal` (D-43).

## Prerequisites (clean machine)
1. **Docker Desktop** (Mac/Windows) running. `host.docker.internal` -> host loopback is a
   Docker Desktop feature; native-Linux needs `--add-host=host-gateway` (tracked: D-43b).
2. **System Ollama** on `127.0.0.1:11434` with the pinned models (D-11):
   `qwen3:14b` (`bdbd181c33f2`) and `bge-m3` (`790764642607`). Do **not** set `OLLAMA_HOST`.
3. A LanceDB store mounted by `docker-compose.yml` (synthetic only outside M6).

## Bring up / tear down
```bash
deploy/up.sh      # build + compose up -d + health-check http://127.0.0.1:8000/health
deploy/down.sh    # compose down + verify 127.0.0.1:8000 released
```

## Backup + restore drill
The store is git-ignored (D-28); back it up to a local tarball and restore from it.
```bash
# backup a synthetic store
tar -czf /tmp/store.tar.gz -C pipeline/.lancedb_full .

# restore into a SCRATCH dir (default) — never touches the live pipeline/.lancedb
deploy/restore.sh /tmp/store.tar.gz
# -> pipeline/.lancedb_restored

# production restore: pass the real volume path explicitly
# deploy/restore.sh /path/to/store.tar.gz pipeline/.lancedb
```

## Safety invariants (enforced)
- Compose-only — no `docker run -p` (the loopback publish lives in `docker-compose.yml`).
- No `0.0.0.0`, no public port, no tunnel; loopback is the boundary (D-41/D-43a).
- `restore.sh` defaults to a scratch target so the M2-8 baseline store is never clobbered.
- Synthetic/public documents only; real data is M6 (onsite, written approval).
