"""Cross-platform task runner (Windows-friendly alternative to the Makefile).

Usage:
    uv run python tasks.py <target> [--cities delhi pune]

Targets mirror the Makefile: setup, geo, data, features, train, evaluate, predict,
attribution, actions, pipeline, api, ui, demo, test, snapshot.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PIPELINE_STAGES = {"geo", "data", "features", "train", "evaluate", "predict",
                   "attribution", "actions", "pipeline"}


def sh(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(cwd or ROOT)).returncode


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    target = sys.argv[1]
    cities = sys.argv[sys.argv.index("--cities") + 1:] if "--cities" in sys.argv else ["delhi", "pune"]

    if target == "setup":
        rc = sh(["uv", "sync"])
        return rc or sh(["npm", "install"], cwd=ROOT / "frontend")
    if target in PIPELINE_STAGES:
        stage = "all" if target == "pipeline" else target
        return sh(["uv", "run", "python", "scripts/run_pipeline.py", stage, "--cities", *cities])
    if target == "api":
        return sh(["uv", "run", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"])
    if target == "ui":
        return sh(["npm", "run", "dev"], cwd=ROOT / "frontend")
    if target == "demo":
        api = subprocess.Popen(["uv", "run", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"], cwd=str(ROOT))
        try:
            sh(["npm", "run", "dev"], cwd=ROOT / "frontend")
        finally:
            api.terminate()
        return 0
    if target == "test":
        rc = sh(["uv", "run", "pytest", "-q", "backend/tests"])
        return rc or sh(["npx", "tsc", "--noEmit"], cwd=ROOT / "frontend")
    if target == "snapshot":
        import tarfile
        out = ROOT / "vayunetra_snapshots.tar.gz"
        with tarfile.open(out, "w:gz") as tar:
            tar.add(ROOT / "data" / "snapshots", arcname="snapshots")
        print(f"wrote {out}")
        return 0
    print(f"unknown target '{target}'"); return 1


if __name__ == "__main__":
    raise SystemExit(main())
