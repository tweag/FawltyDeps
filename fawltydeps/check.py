"Compare imports and dependencies"

from itertools import groupby
from pathlib import Path
from typing import List

from fawltydeps.types import (
    DeclaredDependency,
    DependencyComparison,
    FileLocation,
    ParsedImport,
)


def compare_imports_to_dependencies(
    imports: List[ParsedImport], dependencies: List[DeclaredDependency]
) -> DependencyComparison:
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
    undeclared_grouped = {
        name: [
            FileLocation(path=Path(i.source.path), lineno=i.source.lineno) for i in deps
        ]
        for name, deps in groupby(undeclared, key=lambda x: x.name)
    }
    unused = {d.name for d in dependencies if d.name not in imported_names}

    return DependencyComparison(
        undeclared=undeclared_grouped,
        unused=unused,
    )
