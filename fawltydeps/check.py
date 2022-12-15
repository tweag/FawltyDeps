"Compare imports and dependencies"

from typing import List, Tuple, Set
import isort


def compare_imports_to_dependencies(
    imports: List[str], dependencies: List[str]
) -> Tuple[Set[str], Set[str]]:
    """
    Compares imports to dependencies

    Returns set of undeclared non stdlib imports and set of unused dependencies
    """
    non_stdlib_imports: List[str] = list(
        filter(lambda module: isort.place_module(module) != "STDLIB", imports)
    )
    undeclared: Set[str] = set(non_stdlib_imports) - set(dependencies)
    unused: Set[str] = set(dependencies) - set(non_stdlib_imports)
    return undeclared, unused
