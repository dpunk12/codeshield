"""Tests for the CLI surface.

Most subcommands are exercised by routing them through the fake-CLI
mechanism used in test_wrappers.py. The integrity-related subcommands
("manifest" and "verify") use real I/O.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from codeshield import cli as cli_mod


def test_manifest_then_verify_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    manifest_path = tmp_path / "integrity.json"

    rc = cli_mod.main(["manifest", str(root), str(manifest_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Wrote manifest" in out

    rc = cli_mod.main(["verify", str(root), str(manifest_path)])
    assert rc == 0
    assert "Integrity OK" in capsys.readouterr().out


def test_verify_failure_returns_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    manifest_path = tmp_path / "integrity.json"
    cli_mod.main(["manifest", str(root), str(manifest_path)])

    (root / "main.py").write_text("print('tampered')\n", encoding="utf-8")
    rc = cli_mod.main(["verify", str(root), str(manifest_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "modified" in err and "main.py" in err


def test_obfuscate_subcommand_invokes_fake_pyarmor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("x=1\n", encoding="utf-8")
    out = tmp_path / "out"

    fake = tmp_path / "fake_pyarmor.py"
    log = tmp_path / "argv.log"
    fake.write_text(
        textwrap.dedent(
            f"""
            import json, sys
            with open({str(log)!r}, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(sys.argv[1:]))
            sys.exit(0)
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "codeshield.obfuscate._resolve_pyarmor",
        lambda: [sys.executable, str(fake)],
    )

    rc = cli_mod.main(["obfuscate", str(src), str(out), "--entry", "main.py"])
    assert rc == 0
    assert "Obfuscated sources written to" in capsys.readouterr().out
    assert log.exists()


def test_package_subcommand_invokes_fake_pyinstaller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entry = tmp_path / "main.py"
    entry.write_text("x=1\n", encoding="utf-8")

    fake = tmp_path / "fake_pyi.py"
    fake.write_text("import sys; sys.exit(0)\n", encoding="utf-8")
    monkeypatch.setattr(
        "codeshield.package._resolve_pyinstaller",
        lambda: [sys.executable, str(fake)],
    )

    rc = cli_mod.main(
        [
            "package",
            str(entry),
            "--output-dir",
            str(tmp_path / "dist"),
            "--work-dir",
            str(tmp_path / "work"),
            "--name",
            "demo",
        ]
    )
    assert rc == 0
    assert "Executable written to" in capsys.readouterr().out


def test_add_data_parser_rejects_bad_format(tmp_path: Path) -> None:
    # argparse converts ArgumentTypeError into SystemExit(2).
    with pytest.raises(SystemExit) as exc_info:
        cli_mod.main(
            [
                "package",
                str(tmp_path),
                "--add-data",
                "no-separator-here",
            ]
        )
    assert exc_info.value.code == 2


def test_version_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_mod.main(["--version"])
    assert exc_info.value.code == 0
    assert "codeshield" in capsys.readouterr().out
