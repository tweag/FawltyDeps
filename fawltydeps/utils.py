"""Common utilities."""

import logging
import sys
from collections.abc import Iterator
from dataclasses import is_dataclass
from itertools import takewhile
from pathlib import Path
from typing import TypeVar

import importlib_metadata

Instance = TypeVar("Instance")
T = TypeVar("T")

logger = logging.getLogger(__name__)


def version() -> str:
    """Return the version of fawltydeps."""
    return str(importlib_metadata.version("fawltydeps"))


def dirs_between(parent: Path, child: Path) -> Iterator[Path]:
    """Return directories between 'parent' and 'child', inclusive.

    Return nothing if 'parent' is not a parent of `child'.
    """
    return takewhile(lambda p: p.is_relative_to(parent), [child, *child.parents])


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
