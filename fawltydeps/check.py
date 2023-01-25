"Compare imports and dependencies"

from itertools import groupby
from typing import List, Tuple

from fawltydeps.types import (
    DeclaredDependency,
    ParsedImport,
    UndeclaredDependency,
    UnusedDependency,
)


def compare_imports_to_dependencies(
    imports: List[ParsedImport], dependencies: List[DeclaredDependency]
) -> Tuple[List[UndeclaredDependency], List[UnusedDependency]]:
    """
    Compares imports to dependencies

    Returns set of undeclared imports and set of unused dependencies.
    For undeclared dependencies returns files and line numbers
    where they were imported in the code.
    """
    imported_names = {i.name for i in imports}
    declared_names = {d.name for d in dependencies}

    undeclared = [i for i in imports if i.name not in declared_names]
    undeclared.sort(key=lambda i: i.name)  # groupby requires pre-sorting
    undeclared_grouped = [
        UndeclaredDependency(name, list(imports))
        for name, imports in groupby(undeclared, key=lambda i: i.name)
    ]

    unused = [d for d in dependencies if d.name not in imported_names]
    unused.sort(key=lambda d: d.name)  # groupby requires pre-sorting
    unused_grouped = [
        UnusedDependency(name, list(deps))
        for name, deps in groupby(unused, key=lambda d: d.name)
    ]

    return undeclared_grouped, unused_grouped
