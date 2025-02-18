"""Types and base classes related to resolving packages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterable, Set, Type, Union

PackageDebugInfo = Union[None, str, Dict[str, Set[str]]]


@dataclass(frozen=True)
class Package:
    """Encapsulate an installable Python package.

    This encapsulates the mapping between a package name (i.e. something you can
    pass to `pip install`) and the import names that it provides once it is
    installed.
    """

    package_name: str  # auto-normalized in .__post_init__()
    import_names: Set[str]
    resolved_with: Type[BasePackageResolver]
    debug_info: PackageDebugInfo = None

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

    def __post_init__(self) -> None:
        """Ensure Package object invariants."""
        object.__setattr__(self, "package_name", self.normalize_name(self.package_name))

    def has_type_stubs(self) -> Set[str]:
        """Return a set of import names without type stubs suffix."""
        provides_stubs_for = [
            import_name[: -len("-stubs")]
            for import_name in self.import_names
            if import_name.endswith("-stubs")
        ]
        return set(provides_stubs_for)

    def is_used(self, imported_names: Iterable[str]) -> bool:
        """Return True iff this package is among the given import names."""
        return bool(self.import_names.intersection(imported_names)) or bool(
            self.has_type_stubs().intersection(imported_names)
        )


class BasePackageResolver(ABC):
    """Define the interface for doing package -> import names lookup."""

    @abstractmethod
    def lookup_packages(self, package_names: Set[str]) -> Dict[str, Package]:
        """Convert package names into corresponding Package objects.

        Resolve as many of the given package names as possible into their
        corresponding import names, and return a dict that maps the resolved
        names to their corresponding Package objects.

        Return an empty dict if this PackageResolver is unable to resolve any
        of the given packages.
        """
        raise NotImplementedError

    def lookup_import(self, import_name: str) -> Iterable[Package]:
        """Convert an import name into Package objects that provide this import.

        This is a convenience helper for when we attempt to suggest a suitable
        package name to depend on, in order to properly declare an undeclared
        import.

        This is the _reverse_ mapping of what .lookup_packages() provides, and
        it is acceptable for a resolver to not provide this functionality (e.g.
        the TemporaryAutoInstallResolver cannot provide this as long as PyPI
        does not allow packages to be queried by provided import names, nor can
        we allow the IdentityMapping to fabricate a nonsense package name based
        on the given import name).
        """
        raise NotImplementedError
