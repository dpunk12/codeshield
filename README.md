# codeshield

Python IP-protection pipeline using **PyArmor** (source obfuscation),
**PyInstaller** (standalone executables), and a built-in **SHA-256 integrity
manifest** (anti-tamper verification).

`codeshield` is a thin, well-tested wrapper around standard tools, plus a
runtime integrity-check module. It does not invent its own crypto or
"unbreakable" obfuscation. Combined, the three layers raise the cost of
reverse engineering and detect modification of the deployed artifact.

## What it does

1. **Obfuscation** — wraps `pyarmor gen` to convert your `.py` files into
   PyArmor's encrypted bytecode form so the source isn't shipped in cleartext.
2. **Integrity manifest** — computes a deterministic SHA-256 manifest over
   the obfuscated tree. At runtime your application can call
   `codeshield.verify_manifest(...)` to detect tampering before running
   anything sensitive.
3. **Packaging** — wraps `pyinstaller` to produce a single-file executable
   for **Windows, macOS, or Linux**. (PyInstaller does not cross-compile;
   build on the target OS, or use a CI matrix.)

## What it is not

* It is not DRM. A determined attacker with the executable can still extract
  bytecode given enough effort. The goal is to make casual reverse
  engineering and redistribution materially harder.
* It does not bypass PyArmor's licensing. Read PyArmor's docs for runtime
  licensing terms before shipping commercially.

## Install

```
pip install -e .[dev]
```

This pulls PyArmor and PyInstaller. On CI, install on the same OS as the
target you are packaging for.

## CLI

```
codeshield obfuscate SRC OUT [--entry main.py]
codeshield manifest  ROOT  MANIFEST.json
codeshield verify    ROOT  MANIFEST.json [--allow-extra]
codeshield package   ENTRY [--name NAME] [--onedir] [--noconsole] \
                          [--add-data SRC:DEST ...] [--hidden-import MOD ...]
codeshield build     SRC ENTRY [--name NAME] [more options]
```

`codeshield build` runs the full pipeline (obfuscate → manifest → package).

## Library API

```python
from codeshield import (
    obfuscate_sources, package_executable,
    build_manifest, verify_manifest, IntegrityError,
)
```

See module docstrings for full parameter docs.

## Runtime tamper check

After packaging, the obfuscated tree contains `integrity.json`. In your
entry script, before running sensitive code:

```python
from pathlib import Path
from codeshield.integrity import verify_manifest, IntegrityError

root = Path(__file__).resolve().parent
try:
    verify_manifest(root, root / "integrity.json")
except IntegrityError as exc:
    raise SystemExit(f"Integrity check failed: {exc}")
```

## Example

See [`examples/hello_app/`](examples/hello_app/) for a minimal end-to-end
demo and its README.

## Cross-platform notes

* Build on each target OS (Windows / macOS / Linux). PyInstaller produces
  native binaries and does not cross-compile.
* `--add-data` uses `:` as the separator on macOS/Linux and `;` on Windows.
  The CLI inserts the right one for you.

## Tests

```
pytest
```

## License

MIT.

