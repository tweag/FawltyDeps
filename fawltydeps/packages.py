"""Encapsulate the lookup of packages and their provided import names."""

import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, Optional, Set

from fawltydeps.utils import hide_dataclass_fields

# importlib.metadata.packages_distributions() was introduced in v3.10, but it
# is not able to infer import names for modules lacking a top_level.txt until
# v3.11. Hence we prefer importlib_metadata in v3.10 as well as pre-v3.10.
if sys.version_info >= (3, 11):
    from importlib.metadata import packages_distributions
else:
    from importlib_metadata import packages_distributions

logger = logging.getLogger(__name__)


class DependenciesMapping(str, Enum):
    """Types of dependency and imports mapping"""

    IDENTITY = "identity"
    LOCAL_ENV = "local_env"


@dataclass
class Package:
    """Encapsulate an installable Python package.

    This encapsulates the mapping between a package name (i.e. something you can
    pass to `pip install`) and the import names that it provides once it is
    installed.
    """

    package_name: str
    mappings: Dict[DependenciesMapping, Set[str]] = field(default_factory=dict)
    import_names: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        # The .import_names member is entirely redundant, as it can always be
        # calculated from a union of self.mappings.values(). However, it is
        # still used often enough (.is_used() is called once per declared
        # dependency) that it makes sense to pre-calculate it, and rather hide
        # the redundancy from our JSON output
        self.import_names = {name for names in self.mappings.values() for name in names}
        hide_dataclass_fields(self, "import_names")

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
        """Add import names provided by this package.

        Import names must be associated with a DependenciesMapping enum value,
        as keeping track of this is extremely helpful when debugging.
        """
        self.mappings.setdefault(mapping, set()).update(import_names)
        self.import_names.update(import_names)

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
                logger.info(
                    f"Could not find {name!r} in the current environment. Assuming "
                    f"it can be imported as {', '.join(sorted(package.import_names))}"
                )
            ret[name] = package
    return ret
