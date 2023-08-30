"""Compare imports and dependencies to determine undeclared and unused deps."""

import logging
from itertools import groupby
from typing import Dict, List

from fawltydeps.packages import Package
from fawltydeps.settings import Settings
from fawltydeps.types import (
    DeclaredDependency,
    ParsedImport,
    UndeclaredDependency,
    UnusedDependency,
)

logger = logging.getLogger(__name__)


def calculate_undeclared(
    imports: List[ParsedImport],
    resolved_deps: Dict[str, Package],
    settings: Settings,
) -> List[UndeclaredDependency]:
    """Calculate which imports are not covered by declared dependencies.

    Return a list of UndeclaredDependency objects that represent the import
    names in 'imports' that are not found in any of the packages in
    'resolved_deps' (representing declared dependencies).
    """
    declared_names = {name for p in resolved_deps.values() for name in p.import_names}
    undeclared = [
        i
        for i in imports
        if i.name not in declared_names.union(settings.ignore_undeclared)
    ]
    undeclared.sort(key=lambda i: i.name)  # groupby requires pre-sorting
    return [
        UndeclaredDependency(name, [i.source for i in imports])
        for name, imports in groupby(undeclared, key=lambda i: i.name)
    ]


def calculate_unused(
    imports: List[ParsedImport],
    declared_deps: List[DeclaredDependency],
    resolved_deps: Dict[str, Package],
    settings: Settings,
) -> List[UnusedDependency]:
    """Calculate which declared dependencies have no corresponding imports.

    Return a list of UnusedDependency objects that represent the dependencies in
    'declared_deps' for which none of the provided import names (found via
    'resolved_deps') are present in the list of actual 'imports'.
    """
    imported_names = {i.name for i in imports}
    unused = [
        dep
        for dep in declared_deps
        if (dep.name not in settings.ignore_unused)
        and not resolved_deps[dep.name].is_used(imported_names)
    ]
    unused.sort(key=lambda dep: dep.name)  # groupby requires pre-sorting
    return [
        UnusedDependency(name, [dep.source for dep in deps])
        for name, deps in groupby(unused, key=lambda d: d.name)
    ]
