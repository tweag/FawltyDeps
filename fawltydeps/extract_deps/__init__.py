"""Collect declared dependencies of the project."""

import logging
import re
from pathlib import Path
from typing import Callable, Iterable, Iterator, NamedTuple, Optional

from fawltydeps.settings import ParserChoice
from fawltydeps.types import DeclaredDependency, DepsSource, UnparseablePathError

from .environment_yml_parser import parse_environment_yml
from .pixi_toml_parser import parse_pixi_toml
from .pyproject_toml_parser import parse_pyproject_toml
from .requirements_parser import parse_requirements_txt
from .setup_cfg_parser import parse_setup_cfg
from .setup_py_parser import parse_setup_py

logger = logging.getLogger(__name__)


class ParsingStrategy(NamedTuple):
    """Named pairing of an applicability criterion and a dependency parser."""

    applies_to_path: Callable[[Path], bool]
    execute: Callable[[Path], Iterator[DeclaredDependency]]


def first_applicable_parser(path: Path) -> Optional[ParserChoice]:
    """Find the first applicable parser choice for given path."""
    return next(
        (
            choice
            for choice, parser in PARSER_CHOICES.items()
            if parser.applies_to_path(path)
        ),
        None,
    )


PARSER_CHOICES = {
    ParserChoice.PYPROJECT_TOML: ParsingStrategy(
        lambda path: path.name == "pyproject.toml", parse_pyproject_toml
    ),
    ParserChoice.REQUIREMENTS_TXT: ParsingStrategy(
        lambda path: re.compile(r".*requirements.*\.(txt|in)").match(path.name)
        is not None,
        parse_requirements_txt,
    ),
    ParserChoice.SETUP_CFG: ParsingStrategy(
        lambda path: path.name == "setup.cfg", parse_setup_cfg
    ),
    ParserChoice.SETUP_PY: ParsingStrategy(
        lambda path: path.name == "setup.py", parse_setup_py
    ),
    ParserChoice.PIXI_TOML: ParsingStrategy(
        lambda path: path.name == "pixi.toml", parse_pixi_toml
    ),
    ParserChoice.ENVIRONMENT_YML: ParsingStrategy(
        lambda path: path.name == "environment.yml", parse_environment_yml
    ),
}


def parse_source(src: DepsSource) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from supported file types.

    Pass a DepsSource objects which specifies the path to the file containing
    the dependency declarations, as well as a parser choice to select the
    parsing strategy for this file.

    Generate (i.e. yield) a DeclaredDependency object for each dependency found.
    There is no guaranteed ordering on the generated dependencies.
    """
    parser = PARSER_CHOICES[src.parser_choice]
    if not parser.applies_to_path(src.path):
        logger.warning(
            f"Manually applying parser '{src.parser_choice}' to dependencies: {src.path}"
        )
    yield from parser.execute(src.path)


def parse_sources(sources: Iterable[DepsSource]) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from supported file types.

    Pass sources from which to parse dependency declarations.
    """
    for source in sources:
        yield from parse_source(source)


def validate_deps_source(
    path: Path,
    parser_choice: Optional[ParserChoice] = None,
    *,
    filter_by_parser: bool = False,
) -> Optional[DepsSource]:
    """Check if the given file path is a valid source for parsing declared deps.

    - Return the given path as a DepsSource object iff it is a file that we know
      how to parse.
    - Return None if this is a directory that must be traversed further to find
      parseable files within.
    - Raise UnparseablePathError if the given path cannot be parsed.

    The given 'parser_choice' and 'filter_by_parser' determine which file paths
    we consider valid sources, and how they are parsed: With parser_choice=None,
    a file path will use the first matching parser in PARSER_CHOICES above, if
    any. Otherwise - when parser_choice is specified - the file must either
    match this parser (filter_by_parser=True), or this parser will be forced
    even if the file does not match (filter_by_parser=False).
    """
    if path.is_dir():
        return None
    if not path.is_file():
        raise UnparseablePathError(
            ctx="Dependencies declaration path is neither dir nor file", path=path
        )

    if parser_choice is not None:
        # User wants a specific parser, but only if the file matches:
        if filter_by_parser and not PARSER_CHOICES[parser_choice].applies_to_path(path):
            raise UnparseablePathError(
                ctx=f"Path does not match {parser_choice} parser", path=path
            )
    else:  # no parser chosen, automatically determine parser for this path
        parser_choice = first_applicable_parser(path)
    if parser_choice is None:  # no suitable parser given
        raise UnparseablePathError(
            ctx="Parsing given dependencies path isn't supported", path=path
        )
    return DepsSource(path, parser_choice)
