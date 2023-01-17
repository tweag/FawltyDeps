"Compare imports and dependencies"

from typing import List, NamedTuple, Set

import isort

from fawltydeps.extract_dependencies import DeclaredDependency
from fawltydeps.extract_imports import ParsedImport

DependencyComparison = NamedTuple(
    "DependencyComparison", [("undeclared", Set[str]), ("unused", Set[str])]
)


def compare_imports_to_dependencies(
    imports: List[ParsedImport], dependencies: List[DeclaredDependency]
) -> DependencyComparison:
    """
    Compares imports to dependencies

    Returns set of undeclared non stdlib imports and set of unused dependencies
    """
    imports_names = [i.name for i in imports]
    dependencies_names = [d.name for d in dependencies]
    non_stdlib_imports = {
        module for module in imports_names if isort.place_module(module) != "STDLIB"
    }
    unique_dependencies = set(dependencies_names)
    undeclared = non_stdlib_imports - unique_dependencies
    unused = unique_dependencies - non_stdlib_imports
    return DependencyComparison(undeclared, unused)
