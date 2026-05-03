"""Tests for the obfuscate and package wrappers.

We don't run real PyArmor or PyInstaller from unit tests (heavy, network,
license-dependent). Instead, we substitute a fake CLI command that records
its arguments, so we verify that the wrappers build the right argv.
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

from codeshield.obfuscate import ObfuscationError, obfuscate_sources
from codeshield.package import PackagingError, package_executable


def _make_fake_cli(tmp_path: Path, *, exit_code: int = 0) -> tuple[list[str], Path]:
    """Create a Python script that records its argv and returns *exit_code*.

    Returns ``(cmd_prefix, log_path)``. ``cmd_prefix`` is suitable to pass as
    ``pyarmor_cmd`` / ``pyinstaller_cmd`` to the wrappers.
    """
    log_path = tmp_path / "argv.log"
    fake = tmp_path / "fake_cli.py"
    fake.write_text(
        textwrap.dedent(
            f"""
            import json, sys
            with open({str(log_path)!r}, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(sys.argv[1:]) + "\\n")
            sys.exit({exit_code})
            """
        ),
        encoding="utf-8",
    )
    return [sys.executable, str(fake)], log_path


def _read_argv(log_path: Path) -> list[str]:
    import json

    return json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])


# ---------------------------------------------------------------------------
# obfuscate_sources
# ---------------------------------------------------------------------------


def test_obfuscate_sources_passes_directory_when_no_entry(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x=1\n", encoding="utf-8")
    out = tmp_path / "out"

    cmd, log = _make_fake_cli(tmp_path)
    obfuscate_sources(src, out, pyarmor_cmd=cmd)

    argv = _read_argv(log)
    assert argv[0] == "gen"
    assert "--output" in argv
    assert argv[argv.index("--output") + 1] == str(out.resolve())
    assert "--recursive" in argv
    assert argv[-1] == str(src.resolve())


def test_obfuscate_sources_passes_entry_script(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    entry_rel = "main.py"
    (src / entry_rel).write_text("print(1)\n", encoding="utf-8")
    out = tmp_path / "out"

    cmd, log = _make_fake_cli(tmp_path)
    obfuscate_sources(src, out, entry=entry_rel, pyarmor_cmd=cmd)

    argv = _read_argv(log)
    assert argv[-1] == str((src / entry_rel).resolve())


def test_obfuscate_sources_no_recursive_flag(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"
    cmd, log = _make_fake_cli(tmp_path)
    obfuscate_sources(src, out, recursive=False, pyarmor_cmd=cmd)
    assert "--recursive" not in _read_argv(log)


def test_obfuscate_sources_extra_args_appended(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"
    cmd, log = _make_fake_cli(tmp_path)
    obfuscate_sources(src, out, extra_args=["--enable-rft"], pyarmor_cmd=cmd)
    argv = _read_argv(log)
    assert "--enable-rft" in argv


def test_obfuscate_sources_raises_on_missing_source(tmp_path: Path) -> None:
    cmd, _ = _make_fake_cli(tmp_path)
    with pytest.raises(ObfuscationError, match="Source directory does not exist"):
        obfuscate_sources(tmp_path / "nope", tmp_path / "out", pyarmor_cmd=cmd)


def test_obfuscate_sources_raises_on_missing_entry(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    cmd, _ = _make_fake_cli(tmp_path)
    with pytest.raises(ObfuscationError, match="Entry script does not exist"):
        obfuscate_sources(src, tmp_path / "out", entry="missing.py", pyarmor_cmd=cmd)


def test_obfuscate_sources_propagates_nonzero_exit(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    cmd, _ = _make_fake_cli(tmp_path, exit_code=3)
    with pytest.raises(ObfuscationError, match="exit code 3"):
        obfuscate_sources(src, tmp_path / "out", pyarmor_cmd=cmd)


def test_obfuscate_sources_reports_missing_pyarmor(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    with pytest.raises(ObfuscationError, match="PyArmor is not installed"):
        obfuscate_sources(
            src,
            tmp_path / "out",
            pyarmor_cmd=[str(tmp_path / "definitely_does_not_exist")],
        )


# ---------------------------------------------------------------------------
# package_executable
# ---------------------------------------------------------------------------


def test_package_executable_basic(tmp_path: Path) -> None:
    entry = tmp_path / "main.py"
    entry.write_text("print('hi')\n", encoding="utf-8")
    out = tmp_path / "dist"
    work = tmp_path / "work"

    cmd, log = _make_fake_cli(tmp_path)
    package_executable(
        entry,
        output_dir=out,
        work_dir=work,
        name="myapp",
        onefile=True,
        console=True,
        pyinstaller_cmd=cmd,
    )

    argv = _read_argv(log)
    assert "--noconfirm" in argv
    assert "--clean" in argv
    assert "--onefile" in argv
    assert "--noconsole" not in argv
    assert argv[argv.index("--name") + 1] == "myapp"
    assert argv[argv.index("--distpath") + 1] == str(out.resolve())
    assert argv[argv.index("--workpath") + 1] == str(work.resolve())
    assert argv[-1] == str(entry.resolve())


def test_package_executable_onedir_and_noconsole(tmp_path: Path) -> None:
    entry = tmp_path / "main.py"
    entry.write_text("x=1\n", encoding="utf-8")
    cmd, log = _make_fake_cli(tmp_path)
    package_executable(
        entry,
        output_dir=tmp_path / "dist",
        work_dir=tmp_path / "work",
        onefile=False,
        console=False,
        pyinstaller_cmd=cmd,
    )
    argv = _read_argv(log)
    assert "--onefile" not in argv
    assert "--noconsole" in argv


def test_package_executable_add_data_uses_correct_separator(tmp_path: Path) -> None:
    entry = tmp_path / "main.py"
    entry.write_text("x=1\n", encoding="utf-8")
    cmd, log = _make_fake_cli(tmp_path)
    package_executable(
        entry,
        output_dir=tmp_path / "dist",
        work_dir=tmp_path / "work",
        add_data=[("assets/logo.png", "assets")],
        hidden_imports=["pkg_resources.py2_warn"],
        pyinstaller_cmd=cmd,
    )
    argv = _read_argv(log)
    sep = ";" if os.name == "nt" else ":"
    assert f"assets/logo.png{sep}assets" in argv
    assert "--hidden-import" in argv
    assert "pkg_resources.py2_warn" in argv


def test_package_executable_raises_on_missing_entry(tmp_path: Path) -> None:
    cmd, _ = _make_fake_cli(tmp_path)
    with pytest.raises(PackagingError, match="Entry script does not exist"):
        package_executable(
            tmp_path / "nope.py",
            output_dir=tmp_path / "dist",
            work_dir=tmp_path / "work",
            pyinstaller_cmd=cmd,
        )


def test_package_executable_propagates_nonzero_exit(tmp_path: Path) -> None:
    entry = tmp_path / "main.py"
    entry.write_text("x=1\n", encoding="utf-8")
    cmd, _ = _make_fake_cli(tmp_path, exit_code=2)
    with pytest.raises(PackagingError, match="exit code 2"):
        package_executable(
            entry,
            output_dir=tmp_path / "dist",
            work_dir=tmp_path / "work",
            pyinstaller_cmd=cmd,
        )


def test_package_executable_reports_missing_pyinstaller(tmp_path: Path) -> None:
    entry = tmp_path / "main.py"
    entry.write_text("x=1\n", encoding="utf-8")
    with pytest.raises(PackagingError, match="PyInstaller is not installed"):
        package_executable(
            entry,
            output_dir=tmp_path / "dist",
            work_dir=tmp_path / "work",
            pyinstaller_cmd=[str(tmp_path / "definitely_does_not_exist")],
        )
