"""Common types used across FawltyDeps."""

from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set


class ParsedImport(NamedTuple):
    "Import parsed from the source code."
    name: str
    location: Optional[Path]
    lineno: Optional[int]


class DeclaredDependency(NamedTuple):
    "Declared dependencies parsed from configuration-containing files"
    name: str
    location: Path


class FileLocation(NamedTuple):
    "General location details of imports and dependencies occurrence."
    path: Path
    lineno: Optional[int]

    def __str__(self) -> str:
        "Readable representation."
        ret = f"{self.path}"
        if self.lineno is not None:
            ret += f":{self.lineno}"
        return ret


class DependencyComparison(NamedTuple):
    "The results of the analysis performed in the 'check' module."
    undeclared: Dict[str, List[FileLocation]]
    unused: Set[str]
