"""Tests for the integrity manifest module.

These tests exercise real filesystem I/O via pytest's tmp_path fixture
because the module's purpose is precisely to detect on-disk tampering.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeshield.integrity import (
    IntegrityError,
    build_manifest,
    verify_manifest,
)


def _make_tree(root: Path) -> None:
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("# pkg\n", encoding="utf-8")
    (root / "pkg" / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "config.json").write_text('{"a": 1}\n', encoding="utf-8")
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")


def test_build_manifest_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _make_tree(root)
    manifest_path = root / "integrity.json"

    manifest = build_manifest(root, manifest_path)
    assert manifest["algorithm"] == "sha256"
    paths = sorted(e["path"] for e in manifest["entries"])
    assert paths == [
        "data/config.json",
        "main.py",
        "pkg/__init__.py",
        "pkg/core.py",
    ]
    # Manifest must not include itself.
    assert "integrity.json" not in paths
    verify_manifest(root, manifest_path)


def test_verify_detects_modified_file(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _make_tree(root)
    manifest_path = root / "integrity.json"
    build_manifest(root, manifest_path)

    (root / "pkg" / "core.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    with pytest.raises(IntegrityError, match="modified.*pkg/core.py"):
        verify_manifest(root, manifest_path)


def test_verify_detects_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _make_tree(root)
    manifest_path = root / "integrity.json"
    build_manifest(root, manifest_path)

    (root / "pkg" / "core.py").unlink()
    with pytest.raises(IntegrityError, match="missing.*pkg/core.py"):
        verify_manifest(root, manifest_path)


def test_verify_detects_extra_file(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _make_tree(root)
    manifest_path = root / "integrity.json"
    build_manifest(root, manifest_path)

    (root / "pkg" / "extra.py").write_text("# new\n", encoding="utf-8")
    with pytest.raises(IntegrityError, match="Unexpected.*pkg/extra.py"):
        verify_manifest(root, manifest_path)


def test_verify_allow_extra_tolerates_new_files(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _make_tree(root)
    manifest_path = root / "integrity.json"
    build_manifest(root, manifest_path)

    (root / "pkg" / "extra.py").write_text("# new\n", encoding="utf-8")
    # Should not raise.
    verify_manifest(root, manifest_path, allow_extra=True)


def test_verify_rejects_missing_manifest(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _make_tree(root)
    with pytest.raises(IntegrityError, match="Manifest file not found"):
        verify_manifest(root, root / "missing.json")


def test_verify_rejects_corrupt_manifest(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _make_tree(root)
    manifest_path = root / "integrity.json"
    manifest_path.write_text("not json", encoding="utf-8")
    with pytest.raises(IntegrityError, match="unreadable or corrupt"):
        verify_manifest(root, manifest_path)


def test_verify_rejects_unsupported_version(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _make_tree(root)
    manifest_path = root / "integrity.json"
    manifest_path.write_text(
        json.dumps({"version": 999, "algorithm": "sha256", "entries": []}),
        encoding="utf-8",
    )
    with pytest.raises(IntegrityError, match="Unsupported manifest version"):
        verify_manifest(root, manifest_path)


def test_build_manifest_root_must_exist(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_manifest(tmp_path / "does_not_exist", tmp_path / "m.json")


def test_manifest_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    _make_tree(root)
    m1 = build_manifest(root, root / "a.json")
    m2 = build_manifest(root, root / "b.json")
    # Same content, same digests, regardless of which manifest we excluded.
    digests_1 = {e["path"]: e["digest"] for e in m1["entries"] if e["path"] != "b.json"}
    digests_2 = {e["path"]: e["digest"] for e in m2["entries"] if e["path"] != "a.json"}
    assert digests_1 == digests_2
