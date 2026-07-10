"""Connector adapters (v0.3.0, D-81) — user-keyed imports from external services.

One module per vendor in this package. An adapter is three functions plus a
SERVICE metadata dict; the registry discovers them at first use. The D-80
contract binds every adapter: pull ONLY (documents flow in, nothing goes out
but the API calls the user asked for), provenance on every item, credentials
sealed by keyvault and deleted on disconnect.

Adapter module contract:

    SERVICE = {
        "slug": "readai",                # registry key + logo filename
        "name": "Read AI",
        "category": "AI Meeting Notetakers",
        "blurb": "Meeting notes, transcripts, and summaries",
        "fields": [                       # credential inputs shown in the UI
            {"key": "api_key", "label": "API key", "secret": True},
        ],
        "key_steps": ["Sign in at ...", "Open Settings > API ..."],
        "plan_note": "",                  # e.g. "Requires the Business plan"
        "docs_url": "https://...",
    }

    def test(creds) -> str            # account label; raises ConnectorAuthError
    def list_items(creds, since=None) -> [{"id","name","kind","modified","meta"}]
    def fetch_item(creds, item) -> (filename, bytes, provenance_dict)

Errors: raise the taxonomy below and the UI shows the message verbatim — write
messages for the attorney, not the developer.
"""

import importlib
import pkgutil

import httpx

DEFAULT_TIMEOUT = 30.0


class ConnectorError(RuntimeError):
    """Base — message is user-facing."""


class ConnectorAuthError(ConnectorError):
    """Key rejected: wrong, revoked, or expired."""


class ConnectorAccessError(ConnectorError):
    """Key valid but this account/plan/scope cannot reach the content."""


class ConnectorRateLimited(ConnectorError):
    """Vendor rate limit hit; try again later."""


class ConnectorUnavailable(ConnectorError):
    """Vendor unreachable or returned a server error."""


_REGISTRY = None


def registry():
    """slug -> adapter module, discovered once from this package."""
    global _REGISTRY
    if _REGISTRY is None:
        found = {}
        for m in pkgutil.iter_modules(__path__):
            if m.name.startswith("_"):
                continue
            mod = importlib.import_module(f"{__name__}.{m.name}")
            svc = getattr(mod, "SERVICE", None)
            if svc and all(callable(getattr(mod, fn, None))
                           for fn in ("test", "list_items", "fetch_item")):
                found[svc["slug"]] = mod
        _REGISTRY = found
    return _REGISTRY


def get(slug):
    mod = registry().get(slug)
    if mod is None:
        raise ValueError(f"unknown connector service: {slug!r}")
    return mod


def services():
    """SERVICE metadata for every registered adapter (the UI's live list)."""
    return sorted((dict(m.SERVICE) for m in registry().values()),
                  key=lambda s: (s["category"], s["name"]))


# --- shared HTTP (httpx, already a pinned dep) ----------------------------------
# Every adapter call is user-initiated (connect / test / import / sync). The
# answer path never imports this package — the loopback posture of answering
# is untouched (SC-6).

def request(method, url, *, headers=None, params=None, json_body=None,
            timeout=DEFAULT_TIMEOUT, auth=None, follow_redirects=True):
    """One HTTP call with the taxonomy applied to transport + status errors.
    Returns the httpx.Response for 2xx; raises ConnectorError subclasses else."""
    try:
        resp = httpx.request(method, url, headers=headers, params=params,
                             json=json_body, timeout=timeout, auth=auth,
                             follow_redirects=follow_redirects)
    except httpx.TimeoutException:
        raise ConnectorUnavailable("the service did not respond in time")
    except httpx.HTTPError as e:
        raise ConnectorUnavailable(f"could not reach the service ({e.__class__.__name__})")
    if resp.status_code in (401,):
        raise ConnectorAuthError("the service rejected this key — check that it "
                                 "was copied completely and has not been revoked")
    if resp.status_code in (402, 403):
        raise ConnectorAccessError("this key works but the account or plan does "
                                   "not allow this access")
    if resp.status_code == 429:
        raise ConnectorRateLimited("the service is rate-limiting requests — "
                                   "try again in a few minutes")
    if resp.status_code >= 500:
        raise ConnectorUnavailable("the service returned a server error — "
                                   "try again later")
    if resp.status_code >= 400:
        raise ConnectorError(f"the service refused the request "
                             f"(HTTP {resp.status_code})")
    return resp


def get_json(url, **kw):
    resp = request("GET", url, **kw)
    try:
        return resp.json()
    except ValueError:
        raise ConnectorUnavailable("the service returned an unreadable response")


def get_bytes(url, **kw):
    return request("GET", url, **kw).content
