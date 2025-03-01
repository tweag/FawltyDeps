"""Compare imports and dependencies to determine undeclared and unused deps."""

import logging
import re
from collections.abc import Iterable
from itertools import groupby

from fawltydeps.packages import BasePackageResolver, Package, suggest_packages
from fawltydeps.settings import Settings
from fawltydeps.types import (
    DeclaredDependency,
    ParsedImport,
    UndeclaredDependency,
    UnusedDependency,
)

logger = logging.getLogger(__name__)


def is_ignored(name: str, ignore_set: set[str]) -> bool:
    """Return True iff 'name' is in 'ignore_set'."""
    if name in ignore_set:  # common case
        return True
    patterns = [
        ".*".join(re.escape(fragment) for fragment in word.split("*"))
        for word in ignore_set
        if "*" in word
    ]
    return any(re.fullmatch(pattern, name) for pattern in patterns)


def calculate_undeclared(
    imports: list[ParsedImport],
    resolved_deps: dict[str, Package],
    resolvers: Iterable[BasePackageResolver],
    settings: Settings,
) -> list[UndeclaredDependency]:
    """Calculate which imports are not covered by declared dependencies.

    Return a list of UndeclaredDependency objects that represent the import
    names in 'imports' that are not found in any of the packages in
    'resolved_deps' (representing declared dependencies).
    """
    declared_names = {name for p in resolved_deps.values() for name in p.import_names}
    undeclared = [
        i
        for i in imports
        if not is_ignored(i.name, settings.ignore_undeclared)
        and i.name not in declared_names
    ]
    undeclared.sort(key=lambda i: i.name)  # groupby requires pre-sorting
    return [
        UndeclaredDependency(
            name,
            [i.source for i in imports],
            {p.package_name for p in suggest_packages(name, resolvers)},
        )
        for name, imports in groupby(undeclared, key=lambda i: i.name)
    ]


def calculate_unused(
    imports: list[ParsedImport],
    declared_deps: list[DeclaredDependency],
    resolved_deps: dict[str, Package],
    settings: Settings,
) -> list[UnusedDependency]:
    """Calculate which declared dependencies have no corresponding imports.

    Return a list of UnusedDependency objects that represent the dependencies in
    'declared_deps' for which none of the provided import names (found via
    'resolved_deps') are present in the list of actual 'imports'.
    """
    imported_names = {i.name for i in imports}
    unused = [
        dep
        for dep in declared_deps
        if not is_ignored(dep.name, settings.ignore_unused)
        and not resolved_deps[dep.name].is_used(imported_names)
    ]
    unused.sort(key=lambda dep: dep.name)  # groupby requires pre-sorting
    return [
        UnusedDependency(name, [dep.source for dep in deps])
        for name, deps in groupby(unused, key=lambda d: d.name)
    ]
