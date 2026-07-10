"""Connections router (v0.3.0, D-81) — user-keyed connector connections.

The user pastes a credential they created in the vendor's own UI; we test it,
seal it with the Keychain master key, and import documents through the same
path as a manual upload. GET/POST only (the structural lock in test_api stays
intact). Credentials NEVER leave this module unencrypted: list/get responses
carry no credential material, and remove deletes the ciphertext row.
"""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import catalog
import connectors
import connsync
import keyvault

router = APIRouter()


class NewConnection(BaseModel):
    service: str
    credentials: dict
    matter: str = "unfiled"
    sync: bool = False


class TestConnection(BaseModel):
    service: str
    credentials: dict


class ConnectionRef(BaseModel):
    id: int


def _adapter(service):
    try:
        return connectors.get(service)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _run_test(mod, credentials):
    """Adapter test() with the taxonomy mapped to honest HTTP statuses."""
    try:
        return mod.test(credentials)
    except connectors.ConnectorRateLimited as e:
        raise HTTPException(status_code=429, detail=str(e))
    except connectors.ConnectorUnavailable as e:
        raise HTTPException(status_code=502, detail=str(e))
    except connectors.ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/connections/services")
def list_services():
    """Registry metadata: which connectors are LIVE and how to get each key."""
    return {"services": connectors.services()}


@router.get("/connections")
def list_connections():
    out = []
    for row in catalog.list_connections():
        job = connsync.job_status(row["id"])
        svc = connectors.registry().get(row["service"])
        out.append({**row, "job": job,
                    "service_name": svc.SERVICE["name"] if svc else row["service"]})
    return {"connections": out}


@router.post("/connections")
def create_connection(body: NewConnection):
    mod = _adapter(body.service)
    fields = {f["key"] for f in mod.SERVICE.get("fields", [])}
    missing = [k for k in fields if not (body.credentials.get(k) or "").strip()]
    if missing:
        raise HTTPException(status_code=400,
                            detail=f"missing credential field(s): {', '.join(sorted(missing))}")
    if body.matter != "unfiled" and not catalog.get_matter(body.matter):
        raise HTTPException(status_code=400, detail=f"unknown matter: {body.matter!r}")
    label = _run_test(mod, body.credentials)          # never store an untested key
    sealed = keyvault.encrypt_secret(
        json.dumps(body.credentials).encode("utf-8"))
    return catalog.add_connection(body.service, sealed, label=label,
                                  config={"matter": body.matter, "sync": body.sync})


@router.post("/connections/test")
def test_connection(body: TestConnection):
    mod = _adapter(body.service)
    label = _run_test(mod, body.credentials)
    return {"ok": True, "account": label}


@router.post("/connections/import")
def import_connection(body: ConnectionRef):
    if not catalog.get_connection(body.id):
        raise HTTPException(status_code=400, detail=f"unknown connection: {body.id}")
    return {"job": connsync.start_import(body.id)}


@router.get("/connections/import/status")
def import_status(id: int):
    return {"job": connsync.job_status(id)}


@router.post("/connections/remove")
def remove_connection(body: ConnectionRef):
    """Disconnect + delete the sealed credential (D-80). Imported documents stay."""
    catalog.remove_connection(body.id)
    return {"ok": True}
