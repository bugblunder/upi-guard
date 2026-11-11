"""Preflight checks for administrator-trusted model artifacts.

Integrity is not authenticity: an attacker who replaces both metadata and model
can still execute code through joblib. Never accept model uploads from users.
"""
import hashlib
import json
import re
from pathlib import Path

import sklearn

from .features import FEATURE_VERSION


def read_verified_artifact(root, version=None):
    """Validate metadata and return the exact bytes checked before deserialization."""
    root = Path(root).resolve(strict=True)

    def contained(path):
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError("Artifact path escapes the configured root")
        return resolved

    if version is None:
        version = json.loads(contained(root / "active.json").read_text())["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", version):
        raise ValueError("Invalid artifact version")
    folder = contained(root / version)
    report = json.loads(contained(folder / "metrics.json").read_text())
    if report["version"] != version:
        raise ValueError("Model version mismatch")
    if report["feature_version"] != FEATURE_VERSION:
        raise ValueError("Feature contract mismatch")
    if report["sklearn"] != sklearn.__version__:
        raise ValueError("scikit-learn version differs from training")
    model_bytes = contained(folder / "model.joblib").read_bytes()
    if hashlib.sha256(model_bytes).hexdigest() != report["model_sha256"]:
        raise ValueError("Model checksum mismatch")
    return version, report, model_bytes
