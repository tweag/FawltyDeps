"Compare imports and dependencies"

import logging
import sys
from itertools import groupby
from typing import List, Optional, Tuple

from fawltydeps.settings import Settings
from fawltydeps.types import (
    DeclaredDependency,
    DependenciesMapping,
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
    """Lookup of import names exposed by local packages."""

    def __init__(self) -> None:
        """Collect packages distribution mapping

        Packages names are changed to lower case for
        coherent comparison with declared dependencies."""

        self.import_name_to_package_mapping = {
            k: [vv.lower() for vv in v] for k, v in packages_distributions().items()
        }  # Called only _once_

    def lookup_package(self, package: str) -> Optional[Tuple[str, ...]]:
        """Convert a package name to installed import names.

        (Although this function generally works with _all_ packages, we will apply
        it only to the subset that is the dependencies of the current project.)

        Use importlib.metadata to look up the mapping between packages and their
        provided import names, and return the import names associated with the given
        package/distribution name in the current Python environment. This obviously
        depends on which Python environment (e.g. virtualenv) we're calling from.

        Return None if we're unable to find any import names for the given package.
        This is typically because the package is missing from the current
        environment, or because it fails to declare its importable modules.
        """
        ret = [
            import_name
            for import_name, packages in self.import_name_to_package_mapping.items()
            if package.lower() in packages
        ]

        return tuple(ret) or None


def dependency_to_imports_mapping(
    dependency: DeclaredDependency, local_package_lookup: LocalPackageLookup
) -> DeclaredDependency:
    """For a single `DeclaredDependency` map the dependency name

    to imports names exposed by a dependency.
    Create a new `DeclaredDependency` object and with updated
    names of imports and mapping type used.
    """
    import_names = local_package_lookup.lookup_package(dependency.name)
    return (
        dependency.replace_mapping(
            import_names, DependenciesMapping.DEPENDENCY_TO_IMPORT
        )
        if import_names
        # Fallback to IDENTITY mapping
        else dependency
    )


def map_dependencies_to_imports(
    dependencies: List[DeclaredDependency],
) -> List[DeclaredDependency]:
    """Map dependencies names to list of imports names exposed by a package"""

    local_package_lookup = LocalPackageLookup()

    return [
        dependency_to_imports_mapping(d, local_package_lookup) for d in dependencies
    ]


def compare_imports_to_dependencies(
    imports: List[ParsedImport],
    dependencies: List[DeclaredDependency],
    settings: Settings,
) -> Tuple[List[UndeclaredDependency], List[UnusedDependency]]:
    """
    Compares imports to dependencies

    Returns set of undeclared imports and set of unused dependencies.
    For undeclared dependencies returns files and line numbers
    where they were imported in the code.
    """

    # TODO consider empty list of dependency to import
    mapped_dependencies = map_dependencies_to_imports(dependencies)

    names_from_imports = {i.name for i in imports}
    names_from_dependencies = {
        d for dep in mapped_dependencies for d in dep.import_names
    }

    undeclared = [
        i
        for i in imports
        if i.name not in names_from_dependencies.union(settings.ignore_undeclared)
    ]
    undeclared.sort(key=lambda i: i.name)  # groupby requires pre-sorting
    undeclared_grouped = [
        UndeclaredDependency(name, list(imports))
        for name, imports in groupby(undeclared, key=lambda i: i.name)
    ]

    unused = [
        dep
        for dep in mapped_dependencies
        if (dep.name not in settings.ignore_unused)
        and len(set(dep.import_names) & names_from_imports) == 0
    ]
    unused.sort(key=lambda d: d.name)  # groupby requires pre-sorting
    unused_grouped = [
        UnusedDependency(name, list(deps))
        for name, deps in groupby(unused, key=lambda d: d.name)
    ]

    return undeclared_grouped, unused_grouped
