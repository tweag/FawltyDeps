"Compare imports and dependencies"

from itertools import groupby
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set

import isort

from fawltydeps.extract_dependencies import DeclaredDependency
from fawltydeps.extract_imports import ParsedImport


class LocationDetails(NamedTuple):
    "General location details of imports and dependencies occurence."
    location: Path
    lineno: Optional[int]

    def __str__(self) -> str:
        "Readable representation."
        return f"{self.location}:{self.lineno}"


DependencyComparison = NamedTuple(
    "DependencyComparison",
    [
        ("undeclared", Dict[str, List[LocationDetails]]),
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
    imports_names = [i.name for i in imports]
    dependencies_names = [d.name for d in dependencies]
    non_stdlib_imports = {
        module for module in imports_names if isort.place_module(module) != "STDLIB"
    }
    unique_dependencies = set(dependencies_names)
    undeclared = non_stdlib_imports - unique_dependencies
    unused = unique_dependencies - non_stdlib_imports

    imports_without_dependencies = [i for i in imports if i.name in undeclared]

    undeclared_with_details = {
        _import: [
            LocationDetails(location=i.location, lineno=i.lineno)
            for i in _imports
            if i.location
        ]
        for _import, _imports in groupby(
            imports_without_dependencies, key=lambda x: x.name
        )
    }

    return DependencyComparison(
        undeclared=undeclared_with_details,
        unused=unused,
    )
