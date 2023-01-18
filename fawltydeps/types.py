"""Common types used across FawltyDeps."""

from pathlib import Path
from typing import NamedTuple, Optional


class ParsedImport(NamedTuple):
    "Import parsed from the source code."
    name: str
    location: Optional[Path]


class DeclaredDependency(NamedTuple):
    "Declared dependencies parsed from configuration-containing files"
    name: str
    location: Path
