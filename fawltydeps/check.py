"Compare imports and dependencies"

import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from itertools import groupby
from typing import Dict, Iterable, List, Optional, Set, Tuple

from fawltydeps.settings import Settings
from fawltydeps.types import (
    DeclaredDependency,
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


class DependenciesMapping(Enum):
    """Types of dependency and imports mapping"""

    IDENTITY = "IDENTITY"
    LOCAL_ENV = "LOCAL_ENV"


@dataclass
class Package:
    """Encapsulate an installable Python package.

    This encapsulates the mapping between a package name (i.e. something you can
    pass to `pip install`) and the import names that it provides once it is
    installed.
    """

    package_name: str
    import_names: Set[str] = field(default_factory=set)
    mappings: Set[DependenciesMapping] = field(default_factory=set)

    @staticmethod
    def normalize_name(package_name: str) -> str:
        """Perform standard normalization of package names.

        Verbatim package names are not always appropriate to use in various
        contexts: For example, a package can be installed using one spelling
        (e.g. typing-extensions), but once installed, it is presented in the
        context of the local environment with a slightly different spelling
        (e.g. typing_extension).
        """
        return package_name.lower().replace("-", "_")

    def add_import_names(
        self, *import_names: str, mapping: DependenciesMapping
    ) -> None:
        """Add an import name provided by this package."""
        self.import_names.update(import_names)
        self.mappings.add(mapping)

    def add_identity_import(self) -> None:
        """Add identity mapping to this package.

        This builds on an assumption that a package 'foo' installed with e.g.
        `pip install foo`, will also provide an import name 'foo'. This
        assumption does not always hold, but sometimes we don't have much else
        to go on...
        """
        self.add_import_names(
            self.normalize_name(self.package_name),
            mapping=DependenciesMapping.IDENTITY,
        )

    @classmethod
    def identity_mapping(cls, package_name: str) -> "Package":
        """Factory for conveniently creating identity-mapped package object."""
        ret = cls(package_name)
        ret.add_identity_import()
        return ret

    def is_used(self, imported_names: Iterable[str]) -> bool:
        """Return True iff this package is among the given import names."""
        return bool(self.import_names.intersection(imported_names))


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


def compare_imports_to_dependencies(
    imports: List[ParsedImport],
    dependencies: List[DeclaredDependency],
    settings: Settings,
) -> Tuple[List[UndeclaredDependency], List[UnusedDependency]]:
    """Compares imports to dependencies.

    Returns set of undeclared imports and set of unused dependencies.
    For undeclared dependencies returns files and line numbers
    where they were imported in the code.
    """

    # TODO consider empty list of dependency to import
    packages = resolve_dependencies(dep.name for dep in dependencies)

    imported_names = {i.name for i in imports}
    declared_names = {name for p in packages.values() for name in p.import_names}

    undeclared = [
        i
        for i in imports
        if i.name not in declared_names.union(settings.ignore_undeclared)
    ]
    undeclared.sort(key=lambda i: i.name)  # groupby requires pre-sorting
    undeclared_grouped = [
        UndeclaredDependency(name, [i.source for i in imports])
        for name, imports in groupby(undeclared, key=lambda i: i.name)
    ]

    unused = [
        dep
        for dep in dependencies
        if (dep.name not in settings.ignore_unused)
        and not packages[dep.name].is_used(imported_names)
    ]
    unused.sort(key=lambda dep: dep.name)  # groupby requires pre-sorting
    unused_grouped = [
        UnusedDependency(name, [dep.source for dep in deps])
        for name, deps in groupby(unused, key=lambda d: d.name)
    ]

    return undeclared_grouped, unused_grouped
