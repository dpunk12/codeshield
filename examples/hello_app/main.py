"""Example application protected by CodeShield.

Run normally during development:

    python examples/hello_app/main.py

Or build a protected, packaged executable:

    codeshield build examples/hello_app main.py --name hello

The resulting binary lives under ``dist/``.
"""

from __future__ import annotations

import sys
from pathlib import Path


def secret_algorithm(x: int) -> int:
    """Stand-in for the proprietary logic the client wants to protect."""
    # Trivial here so the example stays small; in real use this would be
    # the algorithm whose source you don't want shipped in cleartext.
    return (x * 2654435761) & 0xFFFFFFFF


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    value = int(args[0]) if args else 42
    print(f"Hello from {Path(__file__).name}")
    print(f"secret_algorithm({value}) = {secret_algorithm(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
