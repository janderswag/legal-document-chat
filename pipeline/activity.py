"""Move 0b (D-68) — interactive-priority signal between chat and background ingest.

Bulk ingest saturates the local Ollama with embedding batches, which measurably slows
answer generation (both models share the same compute). The chat routes mark activity
here; the ingest worker defers new jobs while a chat is recent, so the attorney's
question always outranks background indexing. Purely advisory timing state — no
document data, no effect on what is ingested or how."""

import threading
import time

_lock = threading.Lock()
_last_chat = 0.0


def mark_chat():
    """Record that an interactive chat request is active right now."""
    global _last_chat
    with _lock:
        _last_chat = time.monotonic()


def chat_recent(within_s=10.0):
    """True if a chat was marked within the last ``within_s`` seconds."""
    with _lock:
        return (time.monotonic() - _last_chat) < within_s
