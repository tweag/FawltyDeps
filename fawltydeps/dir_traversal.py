"""Utilities for traversing directory structures."""

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, Generic, Iterator, List, NamedTuple, Set, TypeVar

from fawltydeps.utils import dirs_between

T = TypeVar("T")

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True, order=True)
class TraversalStep(Generic[T]):
    """Encapsulate a single step/directory in an ongoing directory traversal.

    This is an expanded variant of the (dirpath, dirnames, filenames) tuple that
    you would iterate over when doing an os.walk() or Path.walk().
    For each directory that is traversed by a DirectoryTraversal object
    (see below), an instance of this class is returned.
    """

    dir: Path  # the current directory being traversed.
    subdirs: FrozenSet[Path]  # unignored subdirs within the current dir
    files: FrozenSet[Path]  # unignored files within the current dir
    attached: List[T]  # data attached to the current dir or any of its parents


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
       /some/dir/subdir and below. To attach multiple pieces of data to a
       single directory, pass all pieces (in order) to .add().
    3. Allow the traversal to adjust itself while in progress. For example,
       while traversing /some/dir we want to be able "skip" a directory
       (including /some/dir or any parent) from (further) traversal. Likewise,
       we should be able to _add_ more directories to the traversal. (For a
       given traversal, re-adding a directory that was already traversed shall
       have no effect, if you want to re-traverse then setup a _new_ traversal.)

    Note that we _do_ assume that the directory structures being traversed
    remain unchanged during traversal. I.e. adding new entries to a directory
    that has otherwise already been traversed will not cause it to traversed
    again.
    """

    to_traverse: Set[Path] = field(default_factory=set)
    skip_dirs: Set[DirId] = field(default_factory=set)  # includes already-traversed
    attached: Dict[DirId, List[T]] = field(default_factory=dict)

    def add(self, dir_path: Path, *attach_data: T) -> None:
        """Add one directory to this traversal, optionally w/attached data.

        - Any attached data will be supplied to the given directory and its
          subdirectories when it is being .traverse()d.
        - Multiple data items may be attached simply by passing them (in order)
          as additional arguments to this method. A directory can also be added
          multiple times with different attached data; all the attached data
          will be supplied (in the order it was added) by .traverse().
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
        self.attached.setdefault(dir_id, []).extend(attach_data)

    def skip_dir(self, dir_path: Path) -> None:
        """Ignore a directory in future traversal.

        The given directory or its subdirectories will _not_ be traversed
        (although explicitly .add()ed subdirectories _will_ be traversed).
        """
        self.skip_dirs.add(DirId.from_path(dir_path))

    def traverse(self) -> Iterator[TraversalStep[T]]:
        """Perform the traversal of the added directories.

        For each directory traverse, yield a TraversalStep object that contains:
        - The path to the current directory being traversed.
        - The set of all (immediate) subdirectories in the current directory.
          This is NOT a mutable list, as you might expect from os.walk();
          instead, to prevent traversing into a subdirectory, you can call
          .skip_dir() with the relevant subdirectory.
        - The set of all files in the current directory.
        - An ordered list of attached data items, for each of the directory
          levels starting at the base directory (the top-most parent directory
          passed to .add()), up to and including the current directory.

        Directories that have already been .skip_dir()ed will not be traversed,
        nor will a directory previously traversed by this instance be traversed
        again.
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
                if DirId.from_path(path) not in self.skip_dirs
            )
            if not remaining:  # nothing left to do
                break
            logger.debug(f"Left to traverse: {remaining}")
            base_dir = remaining[0]
            assert base_dir.is_dir()  # sanity check
            for cur, subdirs, filenames in os.walk(base_dir, followlinks=True):
                cur_dir = Path(cur)
                cur_id = DirId.from_path(cur_dir)
                if cur_id in self.skip_dirs:
                    logger.debug(f"  Ignoring {cur_dir}")
                    subdirs[:] = []  # don't recurse into subdirs
                    continue  # skip to next

                logger.debug(f"  Traversing {cur_dir}")
                self.skip_dirs.add(cur_id)  # don't traverse this dir again
                # At this yield, the caller takes over control, and may modify
                # .to_traverse/.skip_dirs/.attached (typically via .add() or
                # .skip_dir()). We cannot assume anything about their state here.
                yield TraversalStep(
                    cur_dir,
                    frozenset(cur_dir / subdir for subdir in subdirs),
                    frozenset(cur_dir / filename for filename in filenames),
                    list(accumulate_attached_data(base_dir, cur_dir)),
                )
