""" Utilities to share among test modules """

from pathlib import Path
from typing import Any, Iterable, List

from fawltydeps.types import DeclaredDependency, DependenciesMapping, Location


def assert_unordered_equivalence(actual: Iterable[Any], expected: Iterable[Any]):
    assert sorted(actual) == sorted(expected)


def collect_dep_names(deps: Iterable[DeclaredDependency]) -> Iterable[str]:
    return (dep.name for dep in deps)


def deps_factory(*deps: str) -> List[DeclaredDependency]:
    return [
        DeclaredDependency(
            name=dep,
            source=Location(Path("foo")),
            import_names=(dep,),
            mapping=DependenciesMapping.IDENTITY,
        )
        for dep in deps
    ]
