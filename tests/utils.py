""" Utilities to share among test modules """

from typing import Any, Iterable

from fawltydeps.types import DeclaredDependency


def assert_unordered_equivalence(actual: Iterable[Any], expected: Iterable[Any]):
    assert sorted(actual) == sorted(expected)


def collect_dep_names(deps: Iterable[DeclaredDependency]) -> Iterable[str]:
    return (dep.name for dep in deps)
