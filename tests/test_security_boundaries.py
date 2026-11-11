"""Regression tests for artifact trust, feedback integrity and session recovery."""
import csv
import io
import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import select

from upi_guard import ml
from upi_guard.db import User
from upi_guard.features import FEATURE_VERSION, build_features
from upi_guard.feedback import FIELDS, load_snapshot
from upi_guard.scoring import mask

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def artifacts(tmp_path):
    root = tmp_path / "artifacts"
    shutil.copytree(ROOT / "artifacts", root)
    version = json.loads((root / "active.json").read_text())["version"]
    return root, version


@pytest.mark.parametrize("field,value", [("version", "wrong-version"),
    ("feature_version", "invalid"), ("sklearn", "invalid"), ("model_sha256", "0"*64)])
def test_untrusted_metadata_rejected_before_deserialization(artifacts, monkeypatch, field, value):
    root, version = artifacts
    report_path = root / version / "metrics.json"
    report = json.loads(report_path.read_text())
    report[field] = value
    report_path.write_text(json.dumps(report))
    called = []
    monkeypatch.setattr(ml.joblib, "load", lambda _: called.append(True))
    assert ml.ModelStore(root).bundle is None
    assert called == []


@pytest.mark.parametrize("version", ["../outside", "..\\outside", "/absolute", ".", "", None, 7])
def test_invalid_version_never_deserializes(tmp_path, monkeypatch, version):
    (tmp_path / "active.json").write_text(json.dumps({"version": version}))
    called = []
    monkeypatch.setattr(ml.joblib, "load", lambda _: called.append(True))
    assert ml.ModelStore(tmp_path).bundle is None
    assert not called


def test_symlink_escape_never_deserializes(artifacts, tmp_path, monkeypatch):
    root, version = artifacts
    external = tmp_path / "external"
    shutil.move(root / version, external)
    try:
        (root / version).symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this platform")
    called = []
    monkeypatch.setattr(ml.joblib, "load", lambda _: called.append(True))
    assert ml.ModelStore(root).bundle is None
    assert not called


def test_deserializer_receives_verified_bytes(artifacts, monkeypatch):
    root, version = artifacts
    original = (root / version / "model.joblib").read_bytes()
    load = ml.joblib.load
    def intercept(stream):
        assert isinstance(stream, io.BytesIO)
        assert stream.getvalue() == original
        # Replacing the disk file now cannot change the bytes being loaded.
        (root / version / "model.joblib").write_bytes(b"corrupted after verification")
        return load(stream)
    monkeypatch.setattr(ml.joblib, "load", intercept)
    assert ml.ModelStore(root).bundle is not None


def test_failed_activation_keeps_current_pointer(artifacts, monkeypatch):
    from upi_guard.__main__ import main
    root, version = artifacts
    before = (root / "active.json").read_bytes()
    (root / version / "model.joblib").write_bytes(b"not a model")
    monkeypatch.setattr("sys.argv", ["upi_guard", "activate", version, "--artifacts", str(root)])
    with pytest.raises(ValueError, match="Candidate validation failed"):
        main()
    assert (root / "active.json").read_bytes() == before


def test_revoked_session_can_fetch_fresh_csrf(app, authenticated):
    client, headers = authenticated
    with app.extensions["db_factory"]() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        user.active = False
        db.commit()
    result = client.get("/api/csrf")
    assert result.status_code == 200
    assert result.json["csrf_token"] != headers["X-CSRF-Token"]
    assert client.get("/api/transactions").status_code == 401


@pytest.mark.parametrize("identifier", ["abc", "abcd", "abcde", "abcdef", "abcdefg"])
def test_mask_always_hides_part_of_identifier(identifier):
    masked = mask(identifier)
    assert "•••" in masked
    visible = masked.replace("•••", "")
    assert len(visible) < len(identifier)


@pytest.mark.parametrize("mutation", ["duplicate_header", "extra_column", "boolean_feature", "category_mismatch"])
def test_feedback_rejects_malformed_or_conflicting_snapshots(tmp_path, payload, mutation):
    features = build_features(payload, [])
    if mutation == "boolean_feature": features["history_count"] = True
    if mutation == "category_mismatch": features["category"] = "transfer"
    row = dict(transaction_json=json.dumps(payload), features_json=json.dumps(features),
               feature_version=FEATURE_VERSION, fraud_label="1", source="synthetic test",
               label_available_at="2025-01-02T00:00:00Z")
    path = tmp_path / "snapshot.csv"
    with path.open("w", newline="") as file:
        fields = FIELDS + (["source"] if mutation == "duplicate_header" else [])
        writer = csv.writer(file)
        writer.writerow(fields)
        writer.writerow([row[f] for f in fields] + (["extra"] if mutation == "extra_column" else []))
    with pytest.raises(ValueError):
        load_snapshot(path)


@pytest.mark.parametrize("available", ["2024-12-31T00:00:00Z", "2025-01-02T00:00:00"])
def test_direct_training_validates_label_maturity(tmp_path, payload, available):
    rows = [{**payload, "fraud_label": 1, "label_available_at": available}] * 1000
    with pytest.raises(ValueError, match="Label availability"):
        ml.train(rows, tmp_path)
