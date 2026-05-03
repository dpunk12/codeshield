"""End-to-end build pipeline: obfuscate → integrity manifest → package."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .integrity import build_manifest
from .obfuscate import obfuscate_sources
from .package import package_executable


@dataclass
class BuildResult:
    obfuscated_dir: Path
    manifest_path: Path
    output_dir: Path


def build(
    source_dir: str | os.PathLike[str],
    entry: str,
    *,
    work_dir: str | os.PathLike[str] = "build",
    obfuscated_dir: str | os.PathLike[str] = "build/obfuscated",
    output_dir: str | os.PathLike[str] = "dist",
    manifest_name: str = "integrity.json",
    name: str | None = None,
    onefile: bool = True,
    console: bool = True,
    add_data: Iterable[tuple[str, str]] | None = None,
    hidden_imports: Iterable[str] | None = None,
) -> BuildResult:
    """Run the full protection pipeline.

    Steps:
        1. Obfuscate every Python file in *source_dir* with PyArmor, writing
           the protected sources into *obfuscated_dir*.
        2. Build a SHA-256 integrity manifest of the obfuscated tree, so an
           end-user runtime can detect tampering before executing.
        3. Package the obfuscated entry script into a standalone executable
           with PyInstaller.

    *entry* is a path to the main script, **relative to source_dir**.
    """
    src = Path(source_dir).resolve()
    obf = Path(obfuscated_dir).resolve()

    obfuscate_sources(src, obf, entry=entry)

    manifest_path = obf / manifest_name
    build_manifest(obf, manifest_path)

    # PyArmor preserves the relative layout under --output, so the entry
    # script lives at the same relative path inside the obfuscated tree.
    obfuscated_entry = obf / entry
    if not obfuscated_entry.is_file():
        # Some PyArmor configurations flatten output. Fall back to scanning.
        candidates = list(obf.rglob(Path(entry).name))
        if not candidates:
            raise FileNotFoundError(
                f"Could not locate obfuscated entry script for {entry!r} under {obf}"
            )
        obfuscated_entry = candidates[0]

    out = package_executable(
        obfuscated_entry,
        output_dir=output_dir,
        work_dir=work_dir,
        name=name,
        onefile=onefile,
        console=console,
        add_data=add_data,
        hidden_imports=hidden_imports,
    )

    return BuildResult(obfuscated_dir=obf, manifest_path=manifest_path, output_dir=out)
