"Compare imports and dependencies"

from typing import Iterable, NamedTuple, Set
import isort

DependencyComparison = NamedTuple(
    "DependencyComparison", [("undeclared", Set[str]), ("unused", Set[str])]
)


def compare_imports_to_dependencies(
    imports: Iterable[str], dependencies: Iterable[str]
) -> DependencyComparison:
    """
    Compares imports to dependencies

    Returns set of undeclared non stdlib imports and set of unused dependencies
    """
    non_stdlib_imports = {
        module for module in imports if isort.place_module(module) != "STDLIB"
    }
    unique_dependencies = set(dependencies)
    undeclared = non_stdlib_imports - unique_dependencies
    unused = unique_dependencies - non_stdlib_imports
    return DependencyComparison(undeclared, unused)
