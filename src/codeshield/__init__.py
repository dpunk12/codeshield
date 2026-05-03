"""CodeShield: Python IP protection pipeline.

Public API:
    - obfuscate.obfuscate_sources
    - package.package_executable
    - integrity.build_manifest, integrity.verify_manifest
    - pipeline.build
"""

from .integrity import IntegrityError, build_manifest, verify_manifest
from .obfuscate import ObfuscationError, obfuscate_sources
from .package import PackagingError, package_executable
from .pipeline import build

__all__ = [
    "IntegrityError",
    "ObfuscationError",
    "PackagingError",
    "build",
    "build_manifest",
    "obfuscate_sources",
    "package_executable",
    "verify_manifest",
]

__version__ = "0.1.0"
