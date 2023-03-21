"""Traverse a project to identify appropriate inputs to FawltyDeps."""
import logging
from pathlib import Path
from typing import AbstractSet, Dict, Iterator, Optional, Set, Type

from fawltydeps.extract_declared_dependencies import validate_deps_source
from fawltydeps.extract_imports import validate_code_source
from fawltydeps.settings import Settings
from fawltydeps.types import CodeSource, DepsSource, Source, UnparseablePathException
from fawltydeps.utils import walk_dir

logger = logging.getLogger(__name__)


def find_sources(
    settings: Settings,
    source_types: AbstractSet[Type[Source]] = frozenset([CodeSource, DepsSource]),
) -> Iterator[Source]:
    """Traverse files and directories and yield Sources to be parsed.

    Traverse the files and directories configured by the given Settings object,
    and yield the corresponding *Source objects found.
    """

    # Collect any directories we will need to traverse.
    dirs_to_traverse: Dict[Path, Set[Type[Source]]] = {}

    for path_or_special in settings.code if CodeSource in source_types else []:
        # exceptions raised by validate_code_source() are propagated here
        validated: Optional[Source] = validate_code_source(path_or_special)
        if validated is not None:  # parse-able file given directly
            yield validated
        else:  # must traverse directory
            # sanity check: convince mypy that SpecialPath is already handled
            assert isinstance(path_or_special, Path)
            dirs_to_traverse.setdefault(path_or_special, set()).add(CodeSource)

    for path in settings.deps if DepsSource in source_types else []:
        # exceptions raised by validate_deps_source() are propagated here
        validated = validate_deps_source(
            path, settings.deps_parser_choice, filter_by_parser=False
        )
        if validated is not None:  # parse-able file given directly
            yield validated
        else:  # must traverse directory
            dirs_to_traverse.setdefault(path, set()).add(DepsSource)

    for dir_path, types in dirs_to_traverse.items():
        assert len(types) > 0
        for file in walk_dir(dir_path):  # traverse directories only _once_
            if CodeSource in types:
                try:  # catch all exceptions while traversing dirs
                    validated = validate_code_source(file, dir_path)
                    assert validated is not None  # sanity check
                    yield validated
                except UnparseablePathException:  # don't abort directory walk for this
                    pass
            if DepsSource in types:
                try:  # catch all exceptions while traversing dirs
                    validated = validate_deps_source(
                        file, settings.deps_parser_choice, filter_by_parser=True
                    )
                    assert validated is not None  # sanity check
                    yield validated
                except UnparseablePathException:  # don't abort directory walk for this
                    pass
