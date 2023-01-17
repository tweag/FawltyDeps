"Compare imports and dependencies"

from typing import Iterable, NamedTuple, Set

DependencyComparison = NamedTuple(
    "DependencyComparison", [("undeclared", Set[str]), ("unused", Set[str])]
)


def compare_imports_to_dependencies(
    imports: Iterable[str], dependencies: Iterable[str]
) -> DependencyComparison:
    """
    Compares imports to dependencies

    Returns set of undeclared imports and set of unused dependencies.
    """
    unique_imports = set(imports)
    unique_dependencies = set(dependencies)
    undeclared = unique_imports - unique_dependencies
    unused = unique_dependencies - unique_imports
    return DependencyComparison(undeclared, unused)
