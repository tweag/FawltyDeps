""" Utilities to share among test modules """

from typing import Any, Iterable

from fawltydeps.types import DeclaredDependency


def assert_unordered_equivalence(actual: Iterable[Any], expected: Iterable[Any]):
    assert sorted(actual) == sorted(expected)


def collect_dep_names_sorted(deps: Iterable[DeclaredDependency]):
    return sorted(dep.name for dep in deps)
