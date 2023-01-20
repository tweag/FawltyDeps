"Compare imports and dependencies"

from itertools import groupby
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set

import isort

from fawltydeps.extract_dependencies import DeclaredDependency
from fawltydeps.extract_imports import ParsedImport


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


DependencyComparison = NamedTuple(
    "DependencyComparison",
    [
        ("undeclared", Dict[str, List[FileLocation]]),
        ("unused", Set[str]),
    ],
)


def compare_imports_to_dependencies(
    imports: List[ParsedImport], dependencies: List[DeclaredDependency]
) -> DependencyComparison:
    """
    Compares imports to dependencies

    Returns set of undeclared non stdlib imports and set of unused dependencies.
    For undeclared dependencies returns files and line numbers
    where they were imported in the code.
    """

    def is_stdlib_import(name: str) -> bool:
        return isort.place_module(name) == "STDLIB"

    imports_non_stdlib = [i for i in imports if not is_stdlib_import(i.name)]

    imported_names = {i.name for i in imports_non_stdlib}
    declared_names = {d.name for d in dependencies}

    undeclared = [i for i in imports_non_stdlib if i.name not in declared_names]
    undeclared.sort(key=lambda i: i.name)  # groupby requires pre-sorting
    undeclared_grouped = {
        name: [
            FileLocation(path=i.location, lineno=i.lineno) for i in deps if i.location
        ]
        for name, deps in groupby(undeclared, key=lambda x: x.name)
    }
    unused = {d.name for d in dependencies if d.name not in imported_names}

    return DependencyComparison(
        undeclared=undeclared_grouped,
        unused=unused,
    )
