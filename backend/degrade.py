"""Honest degradation / diagnosis logging (BUILD_SPEC §1.2, §1.3).

Non-blocking failures and deliberate fallbacks are appended to docs/DEGRADATIONS.md
so the demo can state exactly what degraded. Never used to hide fabricated data.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.config import DOCS_DIR


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def log_degradation(component: str, message: str) -> None:
    """Append a degradation note to docs/DEGRADATIONS.md."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = DOCS_DIR / "DEGRADATIONS.md"
    if not path.exists():
        path.write_text(
            "# Degradations & fallbacks\n\n"
            "Every non-blocking failure or deliberate fallback taken during the build "
            "is logged here (BUILD_SPEC §1.3). An empty list is a valid, honest outcome.\n\n",
            encoding="utf-8",
        )
    with path.open("a", encoding="utf-8") as f:
        f.write(f"- **{_timestamp()} · {component}** — {message}\n")


def log_diagnosis(title: str, body: str) -> None:
    """Write/append a diagnosis section to docs/DIAGNOSIS.md (e.g. model < persistence)."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = DOCS_DIR / "DIAGNOSIS.md"
    header = "" if path.exists() else "# Model diagnosis\n\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{header}## {title} ({_timestamp()})\n\n{body}\n\n")
