"""Command-line interface for CodeShield.

Subcommands:
    obfuscate  Run PyArmor over a source tree.
    package    Run PyInstaller over an entry script.
    manifest   Build a SHA-256 integrity manifest for a directory.
    verify     Verify a directory against an existing manifest.
    build      Run the full obfuscate → manifest → package pipeline.

The CLI is designed to be screen-reader-friendly:

    * One option per line in the help text.
    * Plain text output, no spinners or color codes by default.
    * Every command prints exactly one summary line on success that names
      the artifact it produced, so you don't need to inspect directories
      visually to confirm what happened.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .integrity import IntegrityError, build_manifest, verify_manifest
from .obfuscate import ObfuscationError, obfuscate_sources
from .package import PackagingError, package_executable
from .pipeline import build as run_pipeline


def _parse_data_pair(value: str) -> tuple[str, str]:
    if ":" not in value and ";" not in value:
        raise argparse.ArgumentTypeError(
            f"--add-data must be SRC:DEST (or SRC;DEST on Windows): {value!r}"
        )
    sep = ";" if ";" in value else ":"
    src, _, dest = value.partition(sep)
    if not src or not dest:
        raise argparse.ArgumentTypeError(f"Invalid --add-data value: {value!r}")
    return src, dest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codeshield",
        description=(
            "Python IP protection pipeline: obfuscation, integrity, packaging."
        ),
    )
    parser.add_argument("--version", action="version", version=f"codeshield {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # obfuscate
    p_obf = sub.add_parser("obfuscate", help="Obfuscate Python sources with PyArmor.")
    p_obf.add_argument("source_dir", help="Directory containing Python sources.")
    p_obf.add_argument("output_dir", help="Where to write the obfuscated tree.")
    p_obf.add_argument("--entry", help="Entry script path (relative to source_dir).")
    p_obf.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not pass --recursive to PyArmor.",
    )

    # package
    p_pkg = sub.add_parser("package", help="Bundle a script into an executable with PyInstaller.")
    p_pkg.add_argument("entry_script", help="Python script to package.")
    p_pkg.add_argument("--output-dir", default="dist", help="Output directory (default: dist).")
    p_pkg.add_argument("--work-dir", default="build", help="Work directory (default: build).")
    p_pkg.add_argument("--name", help="Executable name (default: derived from entry script).")
    p_pkg.add_argument(
        "--onedir",
        action="store_true",
        help="Produce a folder bundle instead of --onefile.",
    )
    p_pkg.add_argument(
        "--noconsole",
        action="store_true",
        help="Suppress the console window (Windows/macOS GUI apps).",
    )
    p_pkg.add_argument(
        "--add-data",
        action="append",
        type=_parse_data_pair,
        default=[],
        metavar="SRC:DEST",
        help="Add a data file or directory; repeatable.",
    )
    p_pkg.add_argument(
        "--hidden-import",
        action="append",
        default=[],
        metavar="MODULE",
        help="Hidden import for PyInstaller; repeatable.",
    )

    # manifest
    p_man = sub.add_parser("manifest", help="Build a SHA-256 integrity manifest.")
    p_man.add_argument("root", help="Directory to hash.")
    p_man.add_argument("manifest_path", help="Where to write the manifest JSON.")

    # verify
    p_ver = sub.add_parser("verify", help="Verify a directory against a manifest.")
    p_ver.add_argument("root", help="Directory to verify.")
    p_ver.add_argument("manifest_path", help="Existing manifest JSON file.")
    p_ver.add_argument(
        "--allow-extra",
        action="store_true",
        help="Tolerate files in the directory that are not listed in the manifest.",
    )

    # build (full pipeline)
    p_build = sub.add_parser("build", help="Run obfuscate + manifest + package as one pipeline.")
    p_build.add_argument("source_dir", help="Directory containing Python sources.")
    p_build.add_argument("entry", help="Entry script path (relative to source_dir).")
    p_build.add_argument("--name", help="Executable name.")
    p_build.add_argument("--output-dir", default="dist", help="Output directory (default: dist).")
    p_build.add_argument("--work-dir", default="build", help="Work directory (default: build).")
    p_build.add_argument(
        "--obfuscated-dir",
        default="build/obfuscated",
        help="Where to write the obfuscated tree (default: build/obfuscated).",
    )
    p_build.add_argument(
        "--manifest-name",
        default="integrity.json",
        help="Manifest filename inside the obfuscated tree (default: integrity.json).",
    )
    p_build.add_argument("--onedir", action="store_true", help="Produce a folder bundle.")
    p_build.add_argument("--noconsole", action="store_true", help="Suppress console window.")
    p_build.add_argument(
        "--add-data",
        action="append",
        type=_parse_data_pair,
        default=[],
        metavar="SRC:DEST",
    )
    p_build.add_argument(
        "--hidden-import",
        action="append",
        default=[],
        metavar="MODULE",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "obfuscate":
            out = obfuscate_sources(
                args.source_dir,
                args.output_dir,
                entry=args.entry,
                recursive=not args.no_recursive,
            )
            print(f"Obfuscated sources written to: {out}")
            return 0

        if args.command == "package":
            out = package_executable(
                args.entry_script,
                output_dir=args.output_dir,
                work_dir=args.work_dir,
                name=args.name,
                onefile=not args.onedir,
                console=not args.noconsole,
                add_data=args.add_data or None,
                hidden_imports=args.hidden_import or None,
            )
            print(f"Executable written to: {out}")
            return 0

        if args.command == "manifest":
            manifest = build_manifest(args.root, args.manifest_path)
            print(
                f"Wrote manifest with {len(manifest['entries'])} entries to: "
                f"{Path(args.manifest_path).resolve()}"
            )
            return 0

        if args.command == "verify":
            verify_manifest(args.root, args.manifest_path, allow_extra=args.allow_extra)
            print(f"Integrity OK: {Path(args.root).resolve()}")
            return 0

        if args.command == "build":
            result = run_pipeline(
                args.source_dir,
                args.entry,
                work_dir=args.work_dir,
                obfuscated_dir=args.obfuscated_dir,
                output_dir=args.output_dir,
                manifest_name=args.manifest_name,
                name=args.name,
                onefile=not args.onedir,
                console=not args.noconsole,
                add_data=args.add_data or None,
                hidden_imports=args.hidden_import or None,
            )
            print(
                "Build complete. "
                f"Obfuscated: {result.obfuscated_dir} | "
                f"Manifest: {result.manifest_path} | "
                f"Executable: {result.output_dir}"
            )
            return 0

    except (ObfuscationError, PackagingError, IntegrityError, FileNotFoundError) as exc:
        # Print to stderr so it shows up cleanly in screen-reader output and
        # so calling shell scripts can capture it without polluting stdout.
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"Unknown command: {args.command!r}")
    return 2  # unreachable, parser.error raises


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
