"""Encapsulate the lookup of packages and their provided import names."""

import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

# importlib_metadata is gradually graduating into the importlib.metadata stdlib
# module, however we rely on internal functions and recent (and upcoming)
# bugfixes that will first be available in the stdlib version in Python v3.12
# (or even later). For now, it is safer for us to _pin_ the 3rd-party dependency
# and use that across all of our supported Python versions.
from importlib_metadata import (
    DistributionFinder,
    MetadataPathFinder,
    _top_level_declared,
    _top_level_inferred,
)

from fawltydeps.utils import hide_dataclass_fields

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
    """Lookup imports exposed by packages installed in a Python environment."""

    def __init__(self, pyenv_path: Optional[Path] = None) -> None:
        """Lookup packages installed in the given virtualenv.

        Default to the current python environment if `pyenv_path` is not given
        (or None).

        Use importlib_metadata to look up the mapping between packages and their
        provided import names.
        """
        if pyenv_path is not None:
            self.pyenv_path = self.determine_package_dir(pyenv_path)
            if self.pyenv_path is None:
                raise ValueError(f"Not a Python env: {pyenv_path}/bin/python missing!")
        else:
            self.pyenv_path = None
        # We enumerate packages for pyenv_path _once_ and cache the result here:
        self._packages: Optional[Dict[str, Package]] = None

    @classmethod
    def determine_package_dir(cls, path: Path) -> Optional[Path]:
        """Return the site-packages directory corresponding to the given path.

        The given 'path' is a user-provided directory path meant to point to
        a Python environment (e.g. a virtualenv, a poetry2nix environment, or
        similar). Deduce the appropriate site-packages directory from this path,
        or return None if no environment could be found at the given path.
        """
        # We define a "valid Python environment" as a directory that contains
        # a bin/python file, and a lib/pythonX.Y/site-packages subdirectory.
        # From there, the returned directory is that site-packages subdir.
        # Note that we must also accept lib/pythonX.Y/site-packages for python
        # versions X.Y that are different from the current Python version.
        if (path / "bin/python").is_file():
            for site_packages in path.glob("lib/python?.*/site-packages"):
                if site_packages.is_dir():
                    return site_packages
        # Given path is not a python environment, but it might be _inside_ one.
        # Try again with parent directory
        return None if path.parent == path else cls.determine_package_dir(path.parent)

    @property
    def packages(self) -> Dict[str, Package]:
        """Return mapping of package names to Package objects.

        This enumerates the available packages in the given Python environment
        (or the current Python environment) _once_, and caches the result for
        the remainder of this object's life.
        """
        if self._packages is None:  # need to build cache
            if self.pyenv_path is None:
                paths = sys.path  # use current Python environment
            else:
                paths = [str(self.pyenv_path)]

            self._packages = {}
            # We're reaching into the internals of importlib_metadata here,
            # which Mypy is not overly fond of. Roughly what we're doing here
            # is calling packages_distributions(), but on a possibly different
            # environment than the current one (i.e. sys.path).
            # Note that packages_distributions() is not able to return packages
            # that map to zero import names.
            context = DistributionFinder.Context(path=paths)  # type: ignore
            for dist in MetadataPathFinder().find_distributions(context):  # type: ignore
                imports = set(
                    _top_level_declared(dist)  # type: ignore
                    or _top_level_inferred(dist)  # type: ignore
                )
                package = Package(dist.name, {DependenciesMapping.LOCAL_ENV: imports})
                self._packages[Package.normalize_name(dist.name)] = package

        return self._packages

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


def resolve_dependencies(
    dep_names: Iterable[str], pyenv_path: Optional[Path] = None
) -> Dict[str, Package]:
    """Associate dependencies with corresponding Package objects.

    Use LocalPackageLookup to find Package objects for each of the given
    dependencies inside the virtualenv given by 'pyenv_path'. When 'pyenv_path'
    is None (the default), look for packages in the current Python environment
    (i.e. equivalent to sys.path).

    For dependencies that cannot be found with LocalPackageLookup,
    fabricate an identity mapping (a pseudo-package making available an import
    of the same name as the package, modulo normalization).

    Return a dict mapping dependency names to the resolved Package objects.
    """
    ret = {}
    local_packages = LocalPackageLookup(pyenv_path)
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
