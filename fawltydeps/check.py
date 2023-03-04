"Compare imports and dependencies"

import logging
import sys
from itertools import groupby
from typing import Dict, Iterable, List, Optional, Tuple

from fawltydeps.settings import Settings
from fawltydeps.types import (
    DeclaredDependency,
    DependenciesMapping,
    Package,
    ParsedImport,
    UndeclaredDependency,
    UnusedDependency,
)

# importlib.metadata.packages_distributions() was introduced in v3.10, but it
# is not able to infer import names for modules lacking a top_level.txt until
# v3.11. Hence we prefer importlib_metadata in v3.10 as well as pre-v3.10.
if sys.version_info >= (3, 11):
    from importlib.metadata import packages_distributions
else:
    from importlib_metadata import packages_distributions

logger = logging.getLogger(__name__)


class LocalPackageLookup:
    """Lookup import names exposed by packages installed in the current venv."""

    def __init__(self) -> None:
        """Collect packages installed in the current python environment.

        Use importlib.metadata to look up the mapping between packages and their
        provided import names. This obviously depends on the Python environment
        (e.g. virtualenv) that we're calling from.
        """
        # We call packages_distributions() only _once here, and build a cache of
        # Package objects from the information extracted.
        self.packages: Dict[str, Package] = {}
        for import_name, package_names in packages_distributions().items():
            for package_name in package_names:
                package = self.packages.setdefault(
                    Package.normalize_name(package_name),
                    Package(package_name),
                )
                package.add_import_names(
                    import_name, mapping=DependenciesMapping.LOCAL_ENV
                )

    def lookup_package(self, package_name: str) -> Optional[Package]:
        """Convert a package name to a locally available Package object.

        (Although this function generally works with _all_ locally available
        packages, we apply it only to the subset that is the dependencies of
        the current project.)

        Return the Package object that encapsulates the package-name-to-import-
        names mapping for the given package name.

        Return None if we're unable to find any import names for the given
        package name. This is typically because the package is missing from the
        current environment, or because we fail to determine its provided import
        names.
        """
        return self.packages.get(Package.normalize_name(package_name))


def resolve_dependencies(dep_names: Iterable[str]) -> Dict[str, Package]:
    """Associate dependencies with corresponding Package objects.

    Use LocalPackageLookup to find Package objects for each of the given
    dependencies. For dependencies that cannot be found with LocalPackageLookup,
    fabricate an identity mapping (a pseudo-package making available an import
    of the same name as the package, modulo normalization).

    Return a dict mapping dependency names to the resolved Package objects.
    """
    ret = {}
    local_packages = LocalPackageLookup()
    for name in dep_names:
        if name not in ret:
            package = local_packages.lookup_package(name)
            if package is None:  # fall back to identity mapping
                package = Package.identity_mapping(name)
            ret[name] = package
    return ret


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
