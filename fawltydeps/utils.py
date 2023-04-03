"""Common utilities"""

import os
from dataclasses import is_dataclass
from functools import wraps
from pathlib import Path
from typing import Callable, Iterator, Optional, TypeVar, no_type_check

import importlib_metadata

Instance = TypeVar("Instance")
T = TypeVar("T")


@no_type_check
def version() -> str:
    """Returns the version of fawltydeps."""

    # This function is extracted to allow annotation with `@no_type_check`.
    # Using `#type: ignore` on the line below leads to an
    # "unused type ignore comment" MyPy error in python's version 3.8 and
    # higher.
    return str(importlib_metadata.version("fawltydeps"))


def walk_dir(path: Path) -> Iterator[Path]:
    """Walk a directory structure and yield Path objects for each file within.

    Wrapper around os.walk() that yields Path objects for files found (directly
    or transitively) under the given directory. Directories whose name start
    with a dot are skipped.
    """
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in files:
            yield Path(root, filename)


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
        for name, value in instance.__dataclass_fields__.items()  # type: ignore
        if name not in field_names
    }
    object.__setattr__(instance, "__dataclass_fields__", remaining_fields)


def calculated_once(method: Callable[[Instance], T]) -> Callable[[Instance], T]:
    """Emulate functools.cached_property for our simple use case.

    functools.cached_property does not exist in Python v3.7, so we emulate the
    simple things we need here:

    Each method that uses this decorator will store its return value in an
    instance attribute whose name is the method name prefixed with underscore.
    The first time the property is referenced, the method will be called, its
    return value stored in the corresponding instance attribute, and also
    returned to the caller. All subsequent references (as long as the stored
    value it not None) will return the instance attribute value directly,
    without calling the method.
    """

    @wraps(method)
    def wrapper(self: Instance) -> T:
        cached_attr = f"_{method.__name__}"
        cached_value: Optional[T] = getattr(self, cached_attr, None)
        if cached_value is not None:
            return cached_value
        calculated: T = method(self)
        setattr(self, cached_attr, calculated)
        return calculated

    return wrapper
