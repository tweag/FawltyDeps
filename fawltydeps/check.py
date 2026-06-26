"""Compare imports and dependencies to determine undeclared and unused deps."""

import logging
import re
from collections.abc import Iterable, Iterator
from itertools import groupby

from fawltydeps.packages import (
    BasePackageResolver,
    Package,
    module_matches,
    suggest_packages,
)
from fawltydeps.settings import Settings
from fawltydeps.types import (
    DeclaredDependency,
    Location,
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


def _prefixes(import_name: str) -> Iterator[str]:
    """Yield 'import_name' and each of its dotted prefixes, shortest first."""
    parts = import_name.split(".")
    for i in range(1, len(parts) + 1):
        yield ".".join(parts[:i])


def _report_name(import_name: str, declared_modules: set[str]) -> str:
    """Return the dotted prefix of 'import_name' to report as undeclared.

    We report the shortest prefix that is not a parent namespace shared with any
    declared module. For an import like "pandas.DataFrame" with nothing declared
    under "pandas", this is simply "pandas". For "google.cloud.bigquery" when
    only "google.cloud.storage" is declared, "google" and "google.cloud" are
    shared namespaces, so we report the distinguishing "google.cloud.bigquery".
    """
    for prefix in _prefixes(import_name):
        if not any(module_matches(declared, prefix) for declared in declared_modules):
            return prefix
    return import_name  # pragma: no cover


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

    Imports are matched against declared dependencies using their full dotted
    import path: an import is covered iff some declared package provides that
    module or one of its parents. This distinguishes packages that share an
    import prefix (e.g. the "google" namespace).
    """
    declared_modules = {
        module for p in resolved_deps.values() for module in p.import_names
    }

    def is_covered(key: str) -> bool:
        return any(prefix in declared_modules for prefix in _prefixes(key))

    # Map each undeclared import (by its reported name) to the source locations
    # where it is imported, preserving import-encounter order.
    undeclared: dict[str, list[Location]] = {}
    for i in imports:
        for key in i.match_keys:
            if is_covered(key):
                continue
            name = _report_name(key, declared_modules)
            if is_ignored(name, settings.ignore_undeclared):
                continue
            sources = undeclared.setdefault(name, [])
            if i.source not in sources:  # avoid dupes from multi-name imports
                sources.append(i.source)

    return [
        UndeclaredDependency(
            name,
            sources,
            {p.package_name for p in suggest_packages(name, resolvers)},
        )
        for name, sources in sorted(undeclared.items())
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
    imported_names = {key for i in imports for key in i.match_keys}
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
