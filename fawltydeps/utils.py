"""Common utilities."""

import logging
import sys
from dataclasses import is_dataclass
from pathlib import Path
from typing import Iterator, TypeVar, no_type_check

import importlib_metadata

Instance = TypeVar("Instance")
T = TypeVar("T")

logger = logging.getLogger(__name__)


@no_type_check
def version() -> str:
    """Return the version of fawltydeps."""
    # This function is extracted to allow annotation with `@no_type_check`.
    # Using `#type: ignore` on the line below leads to an
    # "unused type ignore comment" MyPy error in python's version 3.8 and
    # higher.
    return str(importlib_metadata.version("fawltydeps"))


def dirs_between(parent: Path, child: Path) -> Iterator[Path]:
    """Yield directories between 'parent' and 'child', inclusive."""
    yield child
    if child != parent:
        yield from dirs_between(parent, child.parent)


def hide_dataclass_fields(instance: object, *field_names: str) -> None:
    """Make a dataclass field invisible to asdict() and astuple().

    This also affects e.g. when serializing this dataclass instance to JSON.
    """
    if not is_dataclass(instance) or isinstance(instance, type):
        raise TypeError(f"{instance!r} is not a dataclass instance")
    remaining_fields = {
        name: value
        for name, value in instance.__dataclass_fields__.items()
        if name not in field_names
    }
    object.__setattr__(instance, "__dataclass_fields__", remaining_fields)


def site_packages(venv_dir: Path = Path()) -> Path:
    """Return the site-packages directory of a virtual environment.

    Works for both, Windows and POSIX.
    """
    # Windows
    if sys.platform.startswith("win"):
        return venv_dir / "Lib" / "site-packages"
    # Assume POSIX
    major, minor = sys.version_info[:2]
    return venv_dir / f"lib/python{major}.{minor}/site-packages"
