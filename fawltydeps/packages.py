"""Encapsulate the lookup of packages and their provided import names."""

import logging
import subprocess
import sys
import tempfile
import venv
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set

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

    def is_used(self, imported_names: Iterable[str]) -> bool:
        """Return True iff this package is among the given import names."""
        return bool(self.import_names.intersection(imported_names))


class BasePackageResolver(ABC):
    """Define the interface for doing package -> import names lookup."""

    @abstractmethod
    def lookup_packages(self, package_names: Set[str]) -> Dict[str, Package]:
        """Convert package names into a Package objects with available imports.

        Resolve as many of the given package names as possible into their
        corresponding import names, and return a dict that maps the resolved
        names to their corresponding Package objects.

        Return an empty dict if this PackageResolver is unable to resolve any
        of the given packages.
        """
        raise NotImplementedError


class LocalPackageResolver(BasePackageResolver):
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

    def lookup_packages(self, package_names: Set[str]) -> Dict[str, Package]:
        """Convert package names to locally available Package objects.

        (Although this function generally works with _all_ locally available
        packages, we apply it only to the subset that is the dependencies of
        the current project.)

        Return a dict mapping package names to the Package objects that
        encapsulate the package-name-to-import-names mappings.

        Only return dict entries for the packages that we manage to find in the
        local environment. Omit any packages for which we're unable to determine
        what imports names they provide. This applies to packages that are
        missing from the local environment, or packages where we fail to
        determine its provided import names.
        """
        return {
            name: self.packages[Package.normalize_name(name)]
            for name in package_names
            if Package.normalize_name(name) in self.packages
        }


class TemporaryPipInstallResolver(BasePackageResolver):
    """Resolve packages by installing them in to a temporary venv.

    This provides a resolver for packages that are not installed in an existing
    local environment. This is done by creating a temporary venv, and then
    `pip install`ing the packages into this venv, and then resolving the
    packages in this venv. The venv is automatically deleted before as soon as
    the packages have been resolved."""

    @staticmethod
    @contextmanager
    def temp_installed_requirements(requirements: List[str]) -> Iterator[Path]:
        """Create a temporary venv and install the given requirements into it.

        Provide a path to the temporary venv into the caller's context in which
        the given requirements have been `pip install`ed. Automatically remove
        the venv at the end of the context.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            venv_dir = Path(tmpdir)
            venv.create(venv_dir, clear=True, with_pip=True)
            subprocess.run(
                [f"{venv_dir}/bin/pip", "install", "--no-deps"] + requirements,
                check=True,  # fail if any of the commands fail
            )
            (venv_dir / ".installed").touch()
            yield venv_dir

    def lookup_packages(self, package_names: Set[str]) -> Dict[str, Package]:
        """Convert package names into Package objects via temporary pip install.

        Use the temp_installed_requirements() above to `pip install` the given
        package names into a temporary venv, and then use LocalPackageResolver
        on this venv to provide the Package objects that correspond to the
        package names.
        """
        logger.info("Installing dependencies into a new temporary Python environment.")
        with self.temp_installed_requirements(sorted(package_names)) as venv_dir:
            local_resolver = LocalPackageResolver(venv_dir)
            return local_resolver.lookup_packages(package_names)


class IdentityMapping(BasePackageResolver):
    """An imperfect package resolver that assumes package name == import name.

    This will resolve _any_ package name into a corresponding identical import
    name (modulo normalization, see Package.normalize_name() for details).
    """

    @staticmethod
    def lookup_package(package_name: str) -> Package:
        """Convert a package name into a Package with the same import name."""
        ret = Package(package_name)
        import_name = Package.normalize_name(package_name)
        ret.add_import_names(import_name, mapping=DependenciesMapping.IDENTITY)
        logger.info(
            f"{package_name!r} was not resolved. "
            f"Assuming it can be imported as {import_name!r}."
        )
        return ret

    def lookup_packages(self, package_names: Set[str]) -> Dict[str, Package]:
        """Convert package names into Package objects w/the same import name."""
        return {name: self.lookup_package(name) for name in package_names}


def resolve_dependencies(
    dep_names: Iterable[str],
    pyenv_path: Optional[Path] = None,
    install_deps: bool = False,
) -> Dict[str, Package]:
    """Associate dependencies with corresponding Package objects.

    Use LocalPackageResolver to find Package objects for each of the given
    dependencies inside the virtualenv given by 'pyenv_path'. When 'pyenv_path'
    is None (the default), look for packages in the current Python environment
    (i.e. equivalent to sys.path).

    Return a dict mapping dependency names to the resolved Package objects.
    """
    deps = set(dep_names)  # consume the iterable once

    # This defines the "stack" of resolvers that we will use to convert
    # dependencies into provided import names. We call .lookup_package() on
    # each resolver in order until one of them returns a Package object. At
    # that point we are happy, and don't consult any of the later resolvers.
    resolvers: List[BasePackageResolver] = [LocalPackageResolver(pyenv_path)]
    if install_deps:
        resolvers += [TemporaryPipInstallResolver()]
    # Identity mapping being at the bottom of the resolvers stack ensures that
    # _all_ deps are matched. TODO: If we make the identity mapping optional,
    # we must remember to properly handle/signal unresolved dependencies.
    resolvers += [IdentityMapping()]

    ret: Dict[str, Package] = {}
    for resolver in resolvers:
        unresolved = deps - ret.keys()
        if not unresolved:  # no unresolved deps left
            logger.debug("No dependencies left to resolve!")
            break
        logger.debug(f"Trying to resolve {unresolved!r} with {resolver}")
        resolved = resolver.lookup_packages(unresolved)
        logger.debug(f"  Resolved {resolved!r} with {resolver}")
        ret.update(resolved)
    return ret
