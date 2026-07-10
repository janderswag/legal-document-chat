"""Updates router (UX-8 + v0.3.0 in-place install).
See updates.py for the egress disclosure and updater.py for the
verify-before-swap install pipeline; both run only on user action."""

from fastapi import APIRouter

import updater
import updates

router = APIRouter()


@router.get("/updates/status")
def update_status():
    return updates.status()


@router.post("/updates/install")
def install_update():
    """One-click in-place update (user-clicked; refuses in a dev checkout)."""
    if not updates.status().get("update_available"):
        return {"state": "idle", "detail": "already on the latest version"}
    return updater.start_install()


@router.get("/updates/install/status")
def install_status():
    return updater.status()
