"""Common utilities"""

import logging
import os
from dataclasses import dataclass, field, is_dataclass
from functools import lru_cache, wraps
from pathlib import Path
from typing import (
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    TypeVar,
    no_type_check,
)

import importlib_metadata

Instance = TypeVar("Instance")
T = TypeVar("T")

logger = logging.getLogger(__name__)


@no_type_check
def version() -> str:
    """Returns the version of fawltydeps."""

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


class DirId(NamedTuple):
    """Unique ID for a directory, independent of name/links.

    We use device/inode details from stat() to uniquely identify a directory
    on the current host. This allows us to detect e.g. when we're about to
    traverse the same directory for the second time.
    """

    dev: int
    ino: int

    @classmethod
    @lru_cache()  # Cache stat() calls
    def from_path(cls, path: Path) -> "DirId":
        """Construct DirId from given directory path."""
        dir_stat = path.stat()
        return cls(dir_stat.st_dev, dir_stat.st_ino)


@dataclass
class DirectoryTraversal(Generic[T]):
    """Encapsulate the efficient traversal of a directory structure.

    In short, this is os.walk() on steroids.

    We want to:
    1. Visit a number of (possibly overlapping/nested) directories. We want to
       visit them exactly _once_. We also want to properly handle symlinks to
       directories, including being resistant to infinite traversal loops caused
       by recursive symlinks.
    2. Have data attached to selected directories, and have these pieces of data
       compose as we traverse the directory structure. For example, if we attach
       FOO to directory /some/dir, and attach BAR to directory /some/dir/subdir,
       then we want both FOO and BAR to be available while we traverse
       /some/dir/subdir and below. (To attach multiple pieces of data to a
       single directory, call .add() multiple times.)
    3. Allow the traversal to adjust itself while in progress. For example,
       while traversing /some/dir we want to be able "ignore" a directory
       (including /some/dir or any parent) from (further) traversal. Likewise,
       we should be able to _add_ more directories to the traversal. (For a
       given traversal, re-adding a directory that was already traversed shall
       have no effect, if you want to re-traverse then setup a _new_ traversal.)

    However, we _do_ assume that the directory structures being traversed remain
    unchanged during traversal. I.e. a directory
    """

    to_traverse: Set[Path] = field(default_factory=set)
    to_ignore: Set[DirId] = field(default_factory=set)  # includes already-traversed
    attached: Dict[DirId, List[T]] = field(default_factory=dict)

    def add(self, dir_path: Path, attach_data: Optional[T] = None) -> None:
        """Add one directory to this traversal, optionally w/attached data.

        - Any attached data will be supplied to the given directory and its
          subdirectories when it is being .traverse()d.
        - A directory can be added multiple times with different attached data;
          all the attached data will be supplied (in the order it was added) by
          .traverse().
        - A parent directory and a child directory may both be added with
          different data attached. The child directory will be supplied both the
          parent's data (first) and its own data (last) by .traverse().
        - No matter how many times a directory is added, it will still only be
          traversed _once_. If a directory has already been traversed by this
          instance, it will _not_ be re-traversed.
        """
        if not dir_path.is_dir():
            raise NotADirectoryError(dir_path)
        dir_id = DirId.from_path(dir_path)
        self.to_traverse.add(dir_path)
        if attach_data:
            self.attached.setdefault(dir_id, []).append(attach_data)

    def ignore(self, dir_path: Path) -> None:
        """Ignore a directory in future traversal.

        The given directory or its subdirectories will _not_ be traversed
        (although explicitly .add()ed subdirectories _will_ be traversed).
        """
        self.to_ignore.add(DirId.from_path(dir_path))

    def traverse(self) -> Iterator[Tuple[Path, Set[Path], Set[Path], List[T]]]:
        """Perform the traversal of the added directories.

        For each directory traverse, yield a 4-element tuple consisting of:
        - The path to the current directory being traversed.
        - The set of all (immediate) subdirectories in the current directory.
          This is NOT a mutable list, as you might expect from os.walk();
          instead, to prevent traversing into a subdirectory, you can call
          .ignore() with the relevant subdirectory.
        - The set of all files in the current directory.
        - An ordered list of attached data items, for each of the directory
          levels starting at the base directory (the top-most parent directory
          passed to .add()), up to and including the current directory.

        Directories that have already been .ignore()d will not be traversed, nor
        will a directory previously traversed by this instance be re-traversed.
        """

        def accumulate_attached_data(parent_dir: Path, child_dir: Path) -> Iterator[T]:
            """Yield attached data items for child_dir (starting from parent_dir).

            For each directory level from parent_dir to child_dir (inclusive),
            yield each attached data item in the order they were attached.
            """
            for dir_path in reversed(list(dirs_between(parent_dir, child_dir))):
                for data in self.attached.get(DirId.from_path(dir_path), []):
                    yield data

        while True:
            remaining = sorted(
                path
                for path in self.to_traverse
                if DirId.from_path(path) not in self.to_ignore
            )
            if not remaining:  # nothing left to do
                break
            logger.debug(f"Left to traverse: {remaining}")
            base_dir = remaining[0]
            assert base_dir.is_dir()  # sanity check
            for cur, subdirs, filenames in os.walk(base_dir, followlinks=True):
                cur_dir = Path(cur)
                cur_id = DirId.from_path(cur_dir)
                if cur_id in self.to_ignore:
                    logger.debug(f"  Ignoring {cur_dir}")
                    subdirs[:] = []  # don't recurse into subdirs
                    continue  # skip to next

                logger.debug(f"  Traversing {cur_dir}")
                self.to_ignore.add(cur_id)  # don't re-traverse this dir
                # At this yield, the caller takes over control, and may modify
                # .to_traverse/.to_ignore/.attached (typically via .add() or
                # .ignore()). We cannot assume anything about their state here.
                yield (
                    cur_dir,
                    {cur_dir / subdir for subdir in subdirs},
                    {cur_dir / filename for filename in filenames},
                    list(accumulate_attached_data(base_dir, cur_dir)),
                )


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
