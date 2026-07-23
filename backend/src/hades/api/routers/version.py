"""Version endpoint — the deployed platform version (cheap, unauthenticated)."""

from __future__ import annotations

from fastapi import APIRouter

from hades import __version__

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/version", summary="Deployed platform version")
async def version() -> dict[str, str]:
    return {"name": "hades", "version": __version__}
