"""Utilities for traversing directory structures."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import (
    Dict,
    FrozenSet,
    Generic,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Set,
    TypeVar,
)

from fawltydeps.gitignore_parser import Rule as ExcludeRule
from fawltydeps.gitignore_parser import match_rules, parse_gitignore
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
    @lru_cache()  # Cache stat() calls, but only with absolute paths
    def from_abs_path(cls, abs_path: Path) -> DirId:
        """Construct DirId from given absolute directory path."""
        assert abs_path.is_absolute()  # noqa: S101, sanity check
        dir_stat = abs_path.stat()  # <- expensive
        return cls(dir_stat.st_dev, dir_stat.st_ino)

    @classmethod
    def from_path(cls, path: Path) -> DirId:
        """Construct DirId from given directory path."""
        # Cannot cache calls with relative paths, as caching the result of
        # DirId.from_path(".") is wrong as soon as CWD is changed.
        if not path.is_absolute():
            path = Path.cwd() / path
        return cls.from_abs_path(path)


@dataclass(frozen=True, order=True)
class TraversalStep(Generic[T]):
    """Encapsulate a single step/directory in an ongoing directory traversal.

    This is an expanded variant of the (dirpath, dirnames, filenames) tuple that
    you would iterate over when doing an os.walk() or Path.walk().
    For each directory that is traversed by a DirectoryTraversal object
    (see below), an instance of this class is returned.
    """

    dir: Path  # the current directory being traversed.
    subdirs: FrozenSet[Path]  # non-excluded subdirs within the current dir
    files: FrozenSet[Path]  # non-excluded files within the current dir
    attached: List[T]  # data attached to the current dir or any of its parents
    excluded_subdirs: FrozenSet[Path]  # excluded subdirs within the current dir
    excluded_files: FrozenSet[Path]  # excluded files within the current dir


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
    4. Obey exclude patterns (a la .gitignore) that enable us to exclude parts
       of the directory tree.

    Note that we _do_ assume that the directory structures being traversed
    remain unchanged during traversal. I.e. adding new entries to a directory
    that has otherwise already been traversed will not cause it to traversed
    again.
    """

    to_traverse: Dict[Path, DirId] = field(default_factory=dict)
    skip_dirs: Set[DirId] = field(default_factory=set)  # includes already-traversed
    attached: Dict[DirId, List[T]] = field(default_factory=dict)
    exclude_rules: List[ExcludeRule] = field(default_factory=list)

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
        self.to_traverse[dir_path] = dir_id
        self.attached.setdefault(dir_id, []).extend(attach_data)

    def skip_dir(self, dir_path: Path) -> None:
        """Ignore a directory in future traversal.

        The given directory or its subdirectories will _not_ be traversed
        (although explicitly .add()ed subdirectories _will_ be traversed).
        """
        self.skip_dirs.add(DirId.from_path(dir_path))

    def exclude(self, pattern: str, base_dir: Optional[Path] = None) -> None:
        """Add gitignore-style exclude pattern to this traversal.

        Anchored gitignore rules are taken relative to 'base_dir'. If 'base_dir'
        is not given, the rule cannot be anchored.

        Subdirectories that match an exclude pattern (and have not been .add()ed
        explicitly) will not be traversed, and will also not be part of the
        step.subdirs returned while traversing the parent.

        Files that match an exclude pattern will not be part of the step.files
        returned while traversing the parent.
        """
        logger.debug(f"Parsing rule from pattern {pattern!r}")
        rule = ExcludeRule.from_pattern(pattern.rstrip("\n"), base_dir)

        logger.debug(f"Adding rule {rule!r} @ {rule.base_dir!r}")
        self.exclude_rules.append(rule)

    def exclude_from(self, file_with_exclude_patterns: Path) -> None:
        """Read exclude patterns from the given file and add to this traversal.

        The base_dir is automatically taken to be the directory containing the
        given file.

        Empty lines and comments in this file are automatically skipped,
        but other parse errors from gitignore_parser are propagated.

        See .exclude() for details about how each gitignore pattern is used.
        """
        logger.debug(f"Reading exclude patterns from {file_with_exclude_patterns}...")
        self.exclude_rules = (
            list(parse_gitignore(file_with_exclude_patterns)) + self.exclude_rules
        )

    def is_excluded(self, path: Path, *, is_dir: bool) -> bool:
        """Check if given path is excluded by any of our exclude rules."""
        return match_rules(self.exclude_rules, path, is_dir=is_dir)

    def traverse(self) -> Iterator[TraversalStep[T]]:
        """Perform the traversal of the added directories.

        For each directory traverse, yield a TraversalStep object that contains:
        - The path to the current directory being traversed.
        - The set of all (immediate) subdirectories in the current directory
          that are not excluded. This is a frozenset (NOT a mutable list, as you
          might expect from os.walk()); to prevent traversing into a subdir, you
          should pass the subdir to .skip_dir().
        - The set of all (not excluded) files in the current directory.
        - An ordered list of attached data items, for each of the directory
          levels starting at the base directory (the top-most parent directory
          passed to .add()), up to and including the current directory.
        - The set of excluded subdirs.
        - The set of excluded files.

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
                yield from self.attached.get(DirId.from_path(dir_path), [])

        while True:
            remaining = {
                path: dir_id
                for path, dir_id in self.to_traverse.items()
                if dir_id not in self.skip_dirs
            }
            if not remaining:  # nothing left to do
                break
            logger.debug(f"Left to traverse: {remaining}")
            base_dir = min(remaining.keys())
            assert base_dir.is_dir()  # noqa: S101, sanity check
            for cur, subdirs, filenames in os.walk(base_dir, followlinks=True):
                cur_dir = Path(cur)
                cur_id = DirId.from_path(cur_dir)
                if cur_id in self.skip_dirs:
                    logger.debug(f"  Ignoring {cur_dir}")
                    subdirs[:] = []  # don't recurse into subdirs
                    continue  # skip to next

                logger.debug(f"  Traversing {cur_dir}: {cur_id}")
                self.skip_dirs.add(cur_id)  # don't traverse this dir again

                subdir_paths = {cur_dir / subdir for subdir in subdirs}
                file_paths = {cur_dir / filename for filename in filenames}

                # Process excludes
                exclude_subdirs = {
                    path
                    for path in subdir_paths
                    if self.is_excluded(path, is_dir=True)
                    and (DirId.from_path(path) not in remaining.values())
                }
                for subdir in exclude_subdirs:
                    logger.debug(f"    skip traversing excluded subdir {subdir}")
                    self.skip_dir(subdir)
                exclude_files = {
                    path for path in file_paths if self.is_excluded(path, is_dir=False)
                }

                # At this yield, the caller takes over control, and may modify
                # instance members (typically via .add(), .skip_dir(), or
                # .exclude()). We cannot assume anything about their state here.
                yield TraversalStep(
                    cur_dir,
                    frozenset(subdir_paths - exclude_subdirs),
                    frozenset(file_paths - exclude_files),
                    list(accumulate_attached_data(base_dir, cur_dir)),
                    frozenset(exclude_subdirs),
                    frozenset(exclude_files),
                )
