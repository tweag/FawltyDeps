"""Traverse a project to identify appropriate inputs to FawltyDeps."""
import logging
from pathlib import Path
from typing import AbstractSet, Iterator, Optional, Set, Tuple, Type, Union

from fawltydeps.dir_traversal import DirectoryTraversal
from fawltydeps.extract_declared_dependencies import validate_deps_source
from fawltydeps.extract_imports import validate_code_source
from fawltydeps.packages import validate_pyenv_source
from fawltydeps.settings import Settings
from fawltydeps.types import (
    CodeSource,
    DepsSource,
    PyEnvSource,
    Source,
    UnparseablePathException,
)

logger = logging.getLogger(__name__)


# When setting up the traversal, we .add() directories to be traverse and attach
# information about what we're looking for during the traversal. These are the
# types of data we're allowed to attach:
AttachedData = Union[
    Tuple[Type[CodeSource], Path],  # Look for Python code, with a base_dir
    Type[DepsSource],  # Look for files with dependency declarations
    Type[PyEnvSource],  # Look for Python environments
]


def find_sources(  # pylint: disable=too-many-branches,too-many-statements
    settings: Settings,
    source_types: AbstractSet[Type[Source]] = frozenset(
        [CodeSource, DepsSource, PyEnvSource]
    ),
) -> Iterator[Source]:
    """Traverse files and directories and yield Sources to be parsed.

    Traverse the files and directories configured by the given Settings object,
    and yield the corresponding *Source objects found.

    Some rules/principles:
    - If explicit files are given to settings.code or .deps, these _shall_ never
      be ignored, even if they e.g. are located within a Python environment.
    - If a Python environment (e.g. "path/to/.venv") is explicitly given to
      settings.pyenvs, then we should _not_ look for .code or .deps files within
      that Python environment (with exception of the above rule).
    - When a directory (not directly a Python environment) is given to
      settings.code, .deps, or .pyenvs, we shall traverse that directory
      recursively looking for the respective sources (CodeSource, DepsSource,
      PyEnvSource).
    - When a Python environment is found during the traversal above, we shall
      _not_ look for .code/.deps within that directory.
    - Directories should only be traverse _once_. This includes the case of
      symlinks-to-dirs. We should be resistant to infinite traversal loops
      caused by symlinks. (This is handled by DirectoryTraversal)
    """

    logger.debug("find_sources() Looking for sources under:")
    logger.debug(f"    code:   {settings.code}")
    logger.debug(f"    deps:   {settings.deps}")
    logger.debug(f"    pyenvs: {settings.pyenvs}")

    traversal: DirectoryTraversal[AttachedData] = DirectoryTraversal()

    for path_or_special in settings.code if CodeSource in source_types else []:
        # exceptions raised by validate_code_source() are propagated here
        validated: Optional[Source] = validate_code_source(path_or_special)
        if validated is not None:  # parse-able file given directly
            logger.debug(f"find_sources() Found {validated}")
            yield validated
        else:  # must traverse directory
            # sanity check: convince mypy that SpecialPath is already handled
            assert isinstance(path_or_special, Path)
            # record also base dir for later
            traversal.add(path_or_special, (CodeSource, path_or_special))

    for path in settings.deps if DepsSource in source_types else []:
        # exceptions raised by validate_deps_source() are propagated here
        validated = validate_deps_source(
            path, settings.deps_parser_choice, filter_by_parser=False
        )
        if validated is not None:  # parse-able file given directly
            logger.debug(f"find_sources() Found {validated}")
            yield validated
        else:  # must traverse directory
            traversal.add(path, DepsSource)

    for path in settings.pyenvs if PyEnvSource in source_types else []:
        # exceptions raised by validate_pyenv_source() are propagated here
        package_dirs: Optional[Set[PyEnvSource]] = validate_pyenv_source(path)
        if package_dirs is not None:  # Python environment dir given directly
            logger.debug(f"find_sources() Found {package_dirs}")
            yield from package_dirs
            traversal.skip_dir(path)  # disable traversal of path below
        else:  # must traverse directory to find Python environments
            traversal.add(path, PyEnvSource)

    for step in traversal.traverse():
        for subdir in step.subdirs:  # don't recurse into dot dirs
            if subdir.name.startswith("."):
                traversal.skip_dir(subdir)

        # Extract the Source types we're looking for in this directory.
        # Sanity checks:
        #   - We should not traverse into a directory unless we're looking for
        #     at least _one_ source type.
        #   - We should not be looking for any _other_ source types than those
        #     that were given in our `source_types` argument.
        types = {t[0] if isinstance(t, tuple) else t for t in step.attached}
        assert len(types) > 0
        assert all(t in source_types for t in types)

        if PyEnvSource in types:
            for path in step.subdirs:
                package_dirs = validate_pyenv_source(path)
                if package_dirs is not None:  # pyenvs found here
                    yield from package_dirs
                    traversal.skip_dir(path)  # don't recurse into Python environment
        if CodeSource in types:
            # Retrieve base_dir from closest ancestor, i.e. last CodeSource in .attached:
            base_dir = next(
                (t[1] for t in reversed(step.attached) if isinstance(t, tuple)),
                None,
            )
            assert base_dir is not None  # sanity check: No CodeSource w/o base_dir
            for path in step.files:
                try:  # catch all exceptions while traversing dirs
                    validated = validate_code_source(path, base_dir)
                    assert validated is not None  # sanity check
                    yield validated
                except UnparseablePathException:  # don't abort directory walk for this
                    pass
        if DepsSource in types:
            for path in step.files:
                try:  # catch all exceptions while traversing dirs
                    validated = validate_deps_source(
                        path, settings.deps_parser_choice, filter_by_parser=True
                    )
                    assert validated is not None  # sanity check
                    yield validated
                except UnparseablePathException:  # don't abort directory walk for this
                    pass
