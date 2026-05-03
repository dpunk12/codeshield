"""Standalone executable packaging via PyInstaller.

This wraps the ``pyinstaller`` CLI so we get cross-platform single-file or
single-folder builds. PyInstaller produces native artifacts: a ``.exe`` on
Windows, a Mach-O binary on macOS, and an ELF binary on Linux. The build
must run on the target platform; PyInstaller does not cross-compile.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence


class PackagingError(RuntimeError):
    """Raised when PyInstaller cannot be invoked or returns a non-zero exit code."""


def _resolve_pyinstaller() -> list[str]:
    return [sys.executable, "-m", "PyInstaller"]


def package_executable(
    entry_script: str | os.PathLike[str],
    *,
    output_dir: str | os.PathLike[str] = "dist",
    work_dir: str | os.PathLike[str] = "build",
    name: str | None = None,
    onefile: bool = True,
    console: bool = True,
    add_data: Iterable[tuple[str, str]] | None = None,
    hidden_imports: Iterable[str] | None = None,
    extra_args: Sequence[str] | None = None,
    pyinstaller_cmd: Sequence[str] | None = None,
    clean: bool = True,
) -> Path:
    """Bundle *entry_script* into a standalone executable.

    Parameters
    ----------
    entry_script:
        Path to the Python script that should become the executable's main.
        For obfuscated builds this is typically the PyArmor-generated entry.
    output_dir:
        ``--distpath`` for PyInstaller. Final binary is placed here.
    work_dir:
        ``--workpath`` for PyInstaller (intermediate build files).
    name:
        Optional executable name. Defaults to the entry script's stem.
    onefile:
        If True (default), produce a single-file binary (``--onefile``).
        If False, produce a folder bundle.
    console:
        If False, pass ``--noconsole`` (useful for GUI apps on Windows/macOS).
    add_data:
        Iterable of ``(src, dest)`` pairs added with ``--add-data``. The
        platform-specific separator (``:`` or ``;``) is inserted automatically.
    hidden_imports:
        Module names to pass with ``--hidden-import``.
    extra_args:
        Additional raw arguments forwarded to PyInstaller verbatim.
    pyinstaller_cmd:
        Override for the PyInstaller invocation prefix. Mainly for testing.
    clean:
        If True (default), pass ``--clean`` to remove PyInstaller cache and
        temp files before building, for reproducibility.

    Returns the resolved *output_dir*.
    """
    entry = Path(entry_script).resolve()
    if not entry.is_file():
        raise PackagingError(f"Entry script does not exist: {entry}")

    out = Path(output_dir).resolve()
    work = Path(work_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = list(pyinstaller_cmd) if pyinstaller_cmd else _resolve_pyinstaller()
    cmd += [
        "--noconfirm",
        "--distpath", str(out),
        "--workpath", str(work),
        "--specpath", str(work),
    ]
    if clean:
        cmd.append("--clean")
    if onefile:
        cmd.append("--onefile")
    if not console:
        cmd.append("--noconsole")
    if name:
        cmd += ["--name", name]

    sep = ";" if os.name == "nt" else ":"
    if add_data:
        for src, dest in add_data:
            cmd += ["--add-data", f"{src}{sep}{dest}"]
    if hidden_imports:
        for mod in hidden_imports:
            cmd += ["--hidden-import", mod]
    if extra_args:
        cmd += list(extra_args)

    cmd.append(str(entry))

    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise PackagingError(
            "PyInstaller is not installed or not on PATH. "
            "Install it with: pip install pyinstaller"
        ) from exc

    if completed.returncode != 0:
        raise PackagingError(
            f"PyInstaller failed with exit code {completed.returncode}.\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )

    return out


def pyinstaller_available() -> bool:
    """Return True if a PyInstaller CLI can be invoked from this interpreter."""
    if shutil.which("pyinstaller") is not None:
        return True
    try:
        result = subprocess.run(
            _resolve_pyinstaller() + ["--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
