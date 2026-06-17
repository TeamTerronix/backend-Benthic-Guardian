"""
Resolve PINN model directory for monorepo (../model) or standalone backend repo (./model).
Override with MODEL_DIR env var if needed.
"""

from __future__ import annotations

import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent


def get_model_dir() -> Path:
    override = os.getenv("MODEL_DIR", "").strip()
    if override:
        return Path(override).resolve()

    local = _BACKEND_DIR / "model"
    sibling = _BACKEND_DIR.parent / "model"

    if (local / "pinn_model_best.h5").exists():
        return local
    if (sibling / "pinn_model_best.h5").exists():
        return sibling.resolve()
    return local


MODEL_DIR = get_model_dir()
