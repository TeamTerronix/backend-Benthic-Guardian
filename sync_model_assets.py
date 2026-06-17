"""
sync_model_assets.py
====================
Copy PINN runtime files from a sibling ../model repo (monorepo) into ./model
so the backend repo can deploy alone on Render.

Usage (from backend/):

    python sync_model_assets.py
    python sync_model_assets.py --source /path/to/model
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE = BACKEND_DIR.parent / "model"
TARGET = BACKEND_DIR / "model"

FILES = (
    "forecaster.py",
    "utils.py",
    "scalers.pkl",
    "sensor_info.pkl",
    "pinn_model_best.h5",
    "prediction_results.csv",
    "training_history.csv",
)
DIRS = ("sliot_dataset",)


def sync(source: Path) -> None:
    if not source.is_dir():
        raise SystemExit(f"Source not found: {source}")

    TARGET.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        src = source / name
        if not src.exists():
            print(f"  skip (missing): {name}")
            continue
        shutil.copy2(src, TARGET / name)
        print(f"  copied: {name}")

    for name in DIRS:
        src = source / name
        if not src.is_dir():
            print(f"  skip (missing dir): {name}/")
            continue
        dest = TARGET / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        print(f"  copied: {name}/")

    print(f"Done. Assets in {TARGET}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync model runtime assets into backend/model/")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    print(f"Source: {args.source.resolve()}")
    sync(args.source.resolve())


if __name__ == "__main__":
    main()
