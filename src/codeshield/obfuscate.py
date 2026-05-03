"""Source obfuscation via PyArmor.

This module is a thin, well-tested wrapper around the ``pyarmor`` CLI.
We shell out rather than import PyArmor's internals because:

  * PyArmor's Python API is not part of its supported public surface.
  * Running it as a subprocess matches how it is documented and tested.
  * It keeps PyArmor's licensing and runtime files isolated from our process.

Security notes
--------------
PyArmor 8+ ("pyarmor gen") protects bytecode by encrypting and wrapping it
with a small native runtime. It is the right tool for *making reverse
engineering expensive*; no obfuscator (in any language) makes it impossible.
For defense-in-depth, combine this with :mod:`codeshield.integrity` and
:mod:`codeshield.package`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


class ObfuscationError(RuntimeError):
    """Raised when PyArmor cannot be invoked or returns a non-zero exit code."""


def _resolve_pyarmor() -> list[str]:
    """Return the argv prefix to invoke PyArmor.

    We prefer ``python -m pyarmor.cli`` because that uses the same interpreter
    we're running under, which avoids "PyArmor installed for a different
    Python" mistakes. Fall back to a ``pyarmor`` executable on PATH.
    """
    # `python -m pyarmor.cli` is the supported module entry point in 8.x/9.x.
    # We don't try to import pyarmor here to avoid loading it eagerly.
    return [sys.executable, "-m", "pyarmor.cli"]


def obfuscate_sources(
    source_dir: str | os.PathLike[str],
    output_dir: str | os.PathLike[str],
    *,
    entry: str | None = None,
    recursive: bool = True,
    extra_args: Sequence[str] | None = None,
    pyarmor_cmd: Sequence[str] | None = None,
) -> Path:
    """Obfuscate every Python file under *source_dir* into *output_dir*.

    Parameters
    ----------
    source_dir:
        Directory containing the original Python sources.
    output_dir:
        Directory PyArmor should write the obfuscated tree to. Created if
        missing. Existing contents are not deleted; pass a fresh directory
        for reproducible builds.
    entry:
        Optional path (relative to *source_dir*) of the entry-point script.
        When given, it is passed to PyArmor so its runtime bootstrapping
        is set up correctly.
    recursive:
        If True (default), pass ``-r`` so PyArmor walks the source tree.
    extra_args:
        Additional raw arguments appended after the standard ones, for
        callers who need PyArmor features we don't expose explicitly.
    pyarmor_cmd:
        Override for the PyArmor invocation prefix. Mainly for testing.

    Returns the resolved *output_dir*.
    """
    src = Path(source_dir).resolve()
    if not src.is_dir():
        raise ObfuscationError(f"Source directory does not exist: {src}")

    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = list(pyarmor_cmd) if pyarmor_cmd else _resolve_pyarmor()
    cmd += ["gen", "--output", str(out)]
    if recursive:
        cmd += ["--recursive"]
    if extra_args:
        cmd += list(extra_args)

    # The positional argument to `pyarmor gen` is the entry script or a
    # source directory. If the caller provided an entry script, prefer it,
    # otherwise hand PyArmor the whole directory.
    if entry:
        entry_path = (src / entry).resolve()
        if not entry_path.is_file():
            raise ObfuscationError(f"Entry script does not exist: {entry_path}")
        cmd.append(str(entry_path))
    else:
        cmd.append(str(src))

    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ObfuscationError(
            "PyArmor is not installed or not on PATH. "
            "Install it with: pip install pyarmor"
        ) from exc

    if completed.returncode != 0:
        # Surface PyArmor's own diagnostics; they are usually actionable.
        message = (
            f"PyArmor failed with exit code {completed.returncode}.\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
        raise ObfuscationError(message)

    return out


def pyarmor_available() -> bool:
    """Return True if a ``pyarmor`` CLI can be invoked from this interpreter."""
    if shutil.which("pyarmor") is not None:
        return True
    try:
        result = subprocess.run(
            _resolve_pyarmor() + ["--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
