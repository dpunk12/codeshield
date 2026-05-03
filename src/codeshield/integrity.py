"""Anti-tamper integrity verification.

Builds a SHA-256 manifest over a directory tree and verifies it at runtime.
The manifest itself is stored as a JSON file alongside the protected payload.

This complements PyArmor's own runtime checks: PyArmor protects bytecode from
reverse-engineering, while this module detects modification of any file in
the distribution (including data files, configuration, and the obfuscated
modules themselves).

Typical use:

    # build time
    from codeshield.integrity import build_manifest
    build_manifest("dist/myapp", "dist/myapp/integrity.json")

    # runtime, before doing anything sensitive
    from codeshield.integrity import verify_manifest, IntegrityError
    try:
        verify_manifest("dist/myapp", "dist/myapp/integrity.json")
    except IntegrityError as exc:
        raise SystemExit(f"Tamper detected: {exc}")
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Algorithm name is stored in the manifest so it can be evolved later
# without breaking older deployments.
_HASH_ALGORITHM = "sha256"
_MANIFEST_VERSION = 1
_CHUNK_SIZE = 64 * 1024


class IntegrityError(Exception):
    """Raised when an integrity check fails (missing, extra, or modified file)."""


@dataclass(frozen=True)
class ManifestEntry:
    path: str  # POSIX-style relative path, for cross-platform stability
    size: int
    digest: str


def _iter_files(root: Path, exclude: Iterable[Path]) -> Iterable[Path]:
    """Yield regular files under *root*, deterministically sorted, skipping *exclude*."""
    exclude_resolved = {p.resolve() for p in exclude}
    # os.walk gives us control over traversal order; sort for determinism.
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = Path(dirpath) / name
            try:
                if full.resolve() in exclude_resolved:
                    continue
            except OSError:
                # Broken symlink or permission issue: skip it explicitly
                # rather than silently including a non-readable entry.
                continue
            if full.is_file() and not full.is_symlink():
                yield full


def _hash_file(path: Path) -> tuple[int, str]:
    h = hashlib.new(_HASH_ALGORITHM)
    size = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return size, h.hexdigest()


def build_manifest(root: str | os.PathLike[str], manifest_path: str | os.PathLike[str]) -> dict:
    """Compute a SHA-256 manifest of every regular file under *root*.

    The manifest file itself is excluded from its own contents (otherwise the
    file would have to hash itself, which is impossible).

    Returns the manifest dict that was written.
    """
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise FileNotFoundError(f"Manifest root does not exist: {root_path}")

    manifest_file = Path(manifest_path).resolve()

    entries: list[dict] = []
    for file_path in _iter_files(root_path, exclude=[manifest_file]):
        size, digest = _hash_file(file_path)
        rel = file_path.relative_to(root_path).as_posix()
        entries.append({"path": rel, "size": size, "digest": digest})

    manifest = {
        "version": _MANIFEST_VERSION,
        "algorithm": _HASH_ALGORITHM,
        "entries": entries,
    }

    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    # Write atomically: write to a temp file in the same directory and rename.
    tmp_path = manifest_file.with_suffix(manifest_file.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_path, manifest_file)
    return manifest


def verify_manifest(
    root: str | os.PathLike[str],
    manifest_path: str | os.PathLike[str],
    *,
    allow_extra: bool = False,
) -> None:
    """Verify that *root* matches the manifest stored at *manifest_path*.

    Raises :class:`IntegrityError` on the first detected mismatch with a clear
    message. If *allow_extra* is False (the default), unexpected files inside
    *root* also count as tampering.
    """
    root_path = Path(root).resolve()
    manifest_file = Path(manifest_path).resolve()

    if not manifest_file.is_file():
        raise IntegrityError(f"Manifest file not found: {manifest_file}")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"Manifest is unreadable or corrupt: {exc}") from exc

    if not isinstance(manifest, dict):
        raise IntegrityError("Manifest root must be a JSON object")
    if manifest.get("version") != _MANIFEST_VERSION:
        raise IntegrityError(
            f"Unsupported manifest version: {manifest.get('version')!r}"
        )
    algorithm = manifest.get("algorithm")
    if algorithm != _HASH_ALGORITHM:
        raise IntegrityError(f"Unsupported manifest algorithm: {algorithm!r}")

    expected: dict[str, ManifestEntry] = {}
    for raw in manifest.get("entries", []):
        try:
            entry = ManifestEntry(
                path=str(raw["path"]),
                size=int(raw["size"]),
                digest=str(raw["digest"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise IntegrityError(f"Malformed manifest entry: {raw!r}") from exc
        expected[entry.path] = entry

    seen: set[str] = set()
    for file_path in _iter_files(root_path, exclude=[manifest_file]):
        rel = file_path.relative_to(root_path).as_posix()
        seen.add(rel)
        entry = expected.get(rel)
        if entry is None:
            if allow_extra:
                continue
            raise IntegrityError(f"Unexpected file present: {rel}")
        size, digest = _hash_file(file_path)
        if size != entry.size or digest != entry.digest:
            raise IntegrityError(f"File has been modified: {rel}")

    missing = sorted(set(expected) - seen)
    if missing:
        raise IntegrityError(f"File missing from distribution: {missing[0]}")
