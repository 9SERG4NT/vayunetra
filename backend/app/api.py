"""API routes. Phase 0 provides /health; full endpoints are added in Phase 7."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
