"""Traverse a project to identify appropriate inputs to FawltyDeps."""
import logging
from pathlib import Path
from typing import AbstractSet, Iterator, Optional, Type, Union

from fawltydeps.extract_declared_dependencies import validate_deps_source
from fawltydeps.extract_imports import validate_code_source
from fawltydeps.settings import Settings
from fawltydeps.types import CodeSource, DepsSource, Source, UnparseablePathException
from fawltydeps.utils import DirectoryTraversal

logger = logging.getLogger(__name__)


def find_sources(  # pylint: disable=too-many-branches
    settings: Settings,
    source_types: AbstractSet[Type[Source]] = frozenset([CodeSource, DepsSource]),
) -> Iterator[Source]:
    """Traverse files and directories and yield Sources to be parsed.

    Traverse the files and directories configured by the given Settings object,
    and yield the corresponding *Source objects found.
    """

    logger.debug("find_sources() Looking for sources under:")
    logger.debug(f"    code:   {settings.code}")
    logger.debug(f"    deps:   {settings.deps}")

    traversal: DirectoryTraversal[Union[Type[Source], Path]] = DirectoryTraversal()

    for path_or_special in settings.code if CodeSource in source_types else []:
        # exceptions raised by validate_code_source() are propagated here
        validated: Optional[Source] = validate_code_source(path_or_special)
        if validated is not None:  # parse-able file given directly
            logger.debug(f"find_sources() Found {validated}")
            yield validated
        else:  # must traverse directory
            # sanity check: convince mypy that SpecialPath is already handled
            assert isinstance(path_or_special, Path)
            traversal.add(path_or_special, CodeSource)
            traversal.add(path_or_special, path_or_special)  # also record base dir

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

    for _cur_dir, subdirs, files, extras in traversal.traverse():
        for subdir in subdirs:  # don't recurse into dot dirs
            if subdir.name.startswith("."):
                traversal.ignore(subdir)

        types = {t for t in extras if t in source_types}
        assert len(types) > 0
        if CodeSource in types:
            # Retrieve base_dir from closest ancestor, i.e. last Path in extras
            base_dir = next((x for x in reversed(extras) if isinstance(x, Path)), None)
            assert base_dir is not None  # sanity check: No CodeSource w/o base_dir
            for path in files:
                try:  # catch all exceptions while traversing dirs
                    validated = validate_code_source(path, base_dir)
                    assert validated is not None  # sanity check
                    yield validated
                except UnparseablePathException:  # don't abort directory walk for this
                    pass
        if DepsSource in types:
            for path in files:
                try:  # catch all exceptions while traversing dirs
                    validated = validate_deps_source(
                        path, settings.deps_parser_choice, filter_by_parser=True
                    )
                    assert validated is not None  # sanity check
                    yield validated
                except UnparseablePathException:  # don't abort directory walk for this
                    pass
