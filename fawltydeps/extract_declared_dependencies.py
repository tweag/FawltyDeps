"""Collect declared dependencies of the project"""

import ast
import configparser
import logging
import re
import sys
from pathlib import Path
from typing import Callable, Iterable, Iterator, NamedTuple, Optional, Tuple

from pkg_resources import Requirement

from fawltydeps.limited_eval import CannotResolve, VariableTracker
from fawltydeps.settings import ParserChoice
from fawltydeps.types import (
    DeclaredDependency,
    Location,
    TomlData,
    UnparseablePathException,
)
from fawltydeps.utils import walk_dir

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=E1101
else:
    import tomli as tomllib

logger = logging.getLogger(__name__)

ERROR_MESSAGE_TEMPLATE = "Failed to %s %s %s dependencies in %s: %s"

NamedLocations = Iterator[Tuple[str, Location]]


class DependencyParsingError(Exception):
    """Error raised when parsing of dependency fails"""

    def __init__(self, node: ast.AST):
        super().__init__(node)
        self.node = node


def parse_one_req(req_text: str, source: Location) -> DeclaredDependency:
    """Returns the name of a dependency declared in a requirement specifier."""
    return DeclaredDependency(Requirement.parse(req_text).unsafe_name, source)


def parse_requirements_contents(
    text: str, source: Location
) -> Iterator[DeclaredDependency]:
    """Extract dependencies (packages names) from a requirements file.

    This is usually a requirements.txt file or any other file following the
    Requirements File Format as documented here:
    https://pip.pypa.io/en/stable/reference/requirements-file-format/.
    """
    for line in text.splitlines():
        if (
            not line.lstrip()  # skip empty lines
            or line.lstrip().startswith(("-", "#"))  # skip options and comments
            or ("://" in line.split()[0])  # skip bare URLs at the start of line
        ):
            continue
        yield parse_one_req(line, source)


def parse_setup_contents(text: str, source: Location) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from setup.py.

    This file can contain arbitrary Python code, and simply executing it has
    potential security implications. For now, we parse it with the `ast` module,
    looking for the first call to a `setup()` function, and attempt to extract
    the `install_requires` and `extras_require` keyword args from that function
    call.
    """

    # Attempt to keep track of simple variable assignments (name -> value)
    # declared in the setup.py prior to the setup() call, so that we can
    # resolve any variable references in the arguments to the setup() call.
    tracked_vars = VariableTracker(source)

    def _extract_deps_from_setup_call(node: ast.Call) -> Iterator[DeclaredDependency]:
        for keyword in node.keywords:
            try:
                if keyword.arg == "install_requires":
                    value = tracked_vars.resolve(keyword.value)
                    if not isinstance(value, list):
                        raise DependencyParsingError(keyword.value)
                    for item in value:
                        yield parse_one_req(item, source)
                elif keyword.arg == "extras_require":
                    value = tracked_vars.resolve(keyword.value)
                    if not isinstance(value, dict):
                        raise DependencyParsingError(keyword.value)
                    for items in value.values():
                        for item in items:
                            yield parse_one_req(item, source)
            except (DependencyParsingError, CannotResolve) as exc:
                if sys.version_info >= (3, 9):
                    unparsed_content = ast.unparse(exc.node)  # pylint: disable=E1101
                else:
                    unparsed_content = ast.dump(exc.node)
                logger.warning(
                    f"Could not parse contents of `{keyword.arg}`: {unparsed_content} in {source}."
                )

    def _is_setup_function_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "setup"
        )

    setup_contents = ast.parse(text, filename=str(source.path))
    for node in ast.walk(setup_contents):
        tracked_vars.evaluate(node)
        if _is_setup_function_call(node):
            # Below line is not checked by mypy, but `_is_setup_function_call`
            # makes sure that `node` is of a proper type.
            yield from _extract_deps_from_setup_call(node.value)  # type: ignore
            break


def parse_setup_cfg_contents(
    text: str, source: Location
) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from setup.cfg.

    `ConfigParser` basic building blocks are "sections"
    which are marked by "[..]" in the configuration file.
    Requirements are declared as main dependencies (install_requires),
    extra dependencies (extras_require) and tests dependencies (tests_require).
    See https://setuptools.pypa.io/en/latest/userguide/declarative_config.html
    section: configuring-setup-using-setup-cfg-files for more details.
    The declaration uses `section` + `option` syntax where section may be [options]
    or [options.{requirements_type}].
    """
    parser = configparser.ConfigParser()
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        logger.debug(exc)
        logger.error("Could not parse contents of `%s`", source)
        return

    def parse_value(value: str) -> Iterator[DeclaredDependency]:
        yield from parse_requirements_contents(value, source=source)

    def extract_section(section: str) -> Iterator[DeclaredDependency]:
        if section in parser:
            for option in parser.options(section):
                value = parser.get(section, option)
                logger.debug("Dependencies found in [%s]: %s", section, value)
                yield from parse_value(value)

    def extract_option_from_section(
        section: str, option: str
    ) -> Iterator[DeclaredDependency]:
        if section in parser and option in parser.options(section):
            value = parser.get(section, option)
            logger.debug("Dependencies found in [%s] / %s: %s", section, option, value)
            yield from parse_value(value)

    # Parse [options] -> install_requires
    yield from extract_option_from_section("options", "install_requires")

    # Parse [options] -> extras_require, or [options.extras_require]
    yield from extract_option_from_section("options", "extras_require")
    yield from extract_section("options.extras_require")

    # Parse [options] -> tests_require, or [options.tests_require]
    yield from extract_option_from_section("options", "tests_require")
    yield from extract_section("options.tests_require")


def parse_poetry_pyproject_dependencies(
    poetry_config: TomlData, source: Location
) -> Iterator[DeclaredDependency]:
    """Extract dependencies from `tool.poetry` fields in a pyproject.toml."""

    def parse_main(contents: TomlData, src: Location) -> NamedLocations:
        return (
            (req, src) for req in contents["dependencies"].keys() if req != "python"
        )

    def parse_group(contents: TomlData, src: Location) -> NamedLocations:
        return (
            (req, src)
            for group in contents["group"].values()
            for req in group["dependencies"].keys()
            if req != "python"
        )

    def parse_extra(contents: TomlData, src: Location) -> NamedLocations:
        for group in contents["extras"].values():
            if isinstance(group, list):
                for req in group:
                    yield req, src
            else:
                raise TypeError(f"{group!r} is of type {type(group)}. Expected a list.")

    fields_parsers = [
        ("main", parse_main),
        ("group", parse_group),
        ("extra", parse_extra),
    ]
    yield from parse_pyproject_elements(poetry_config, source, "Poetry", fields_parsers)


def parse_pep621_pyproject_contents(
    parsed_contents: TomlData, source: Location
) -> Iterator[DeclaredDependency]:
    """Extract dependencies from a pyproject.toml using the PEP 621 fields."""

    def parse_main(contents: TomlData, src: Location) -> NamedLocations:
        deps = contents["project"]["dependencies"]
        if isinstance(deps, list):
            for req in deps:
                yield req, src
        else:
            raise TypeError(f"{deps!r} of type {type(deps)}. Expected list.")

    def parse_optional(contents: TomlData, src: Location) -> NamedLocations:
        for group in contents["project"]["optional-dependencies"].values():
            for req in group:
                yield req, src

    fields_parsers = [("main", parse_main), ("optional", parse_optional)]
    return parse_pyproject_elements(parsed_contents, source, "PEP621", fields_parsers)


def parse_pyproject_elements(
    parsed_contents: TomlData,
    source: Location,
    context_name: str,
    named_parsers: Iterable[Tuple[str, Callable[[TomlData, Location], NamedLocations]]],
) -> Iterator[DeclaredDependency]:
    """Use the given data, source, and parsers to step through sections and collect dependencies."""
    for name_field_type, parser in named_parsers:
        try:
            for req, src in parser(parsed_contents, source):
                yield parse_one_req(req, src)
        except KeyError as exc:
            logger.debug(
                ERROR_MESSAGE_TEMPLATE,
                "find",
                context_name,
                name_field_type,
                source,
                exc,
            )
        except (AttributeError, TypeError) as exc:
            logger.error(
                ERROR_MESSAGE_TEMPLATE,
                "parse",
                context_name,
                name_field_type,
                source,
                exc,
            )


def parse_pyproject_contents(
    text: str, source: Location
) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from pyproject.toml.

    There are multiple ways to declare dependencies inside a pyproject.toml.
    We currently handle:
    - PEP 621 core metadata fields
    - Poetry-specific metadata in `tool.poetry` sections.
    """
    parsed_contents = tomllib.loads(text)

    yield from parse_pep621_pyproject_contents(parsed_contents, source)

    if "poetry" in parsed_contents.get("tool", {}):
        yield from parse_poetry_pyproject_dependencies(
            parsed_contents["tool"]["poetry"], source
        )
    else:
        logger.debug("%s does not contain [tool.poetry].", source)


class ParsingStrategy(NamedTuple):
    """Named pairing of an applicability criterion and a dependency parser"""

    applies_to_path: Callable[[Path], bool]
    execute: Callable[[str, Location], Iterator[DeclaredDependency]]


def first_applicable_parser(
    path: Path,
) -> Optional[Tuple[ParserChoice, ParsingStrategy]]:
    """Find the first applicable parser choice for given path."""
    return next(
        (
            (choice, parser)
            for choice, parser in PARSER_CHOICES.items()
            if parser.applies_to_path(path)
        ),
        None,
    )


PARSER_CHOICES = {
    ParserChoice.PYPROJECT_TOML: ParsingStrategy(
        lambda path: path.name == "pyproject.toml", parse_pyproject_contents
    ),
    ParserChoice.REQUIREMENTS_TXT: ParsingStrategy(
        lambda path: re.compile(r".*\brequirements\b.*\.(txt|in)").match(path.name)
        is not None,
        parse_requirements_contents,
    ),
    ParserChoice.SETUP_CFG: ParsingStrategy(
        lambda path: path.name == "setup.cfg", parse_setup_cfg_contents
    ),
    ParserChoice.SETUP_PY: ParsingStrategy(
        lambda path: path.name == "setup.py", parse_setup_contents
    ),
}


def extract_declared_dependencies(
    path: Path, parser_choice: Optional[ParserChoice] = None
) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from supported file types.

    Pass a path from which to discover and parse dependency declarations. Pass
    a directory to traverse that directory tree to find and automatically parse
    any supported files.

    Generate (i.e. yield) a DeclaredDependency object for each dependency found.
    There is no guaranteed ordering on the generated dependencies.
    """

    if path.is_file():
        if parser_choice is not None:
            parser = PARSER_CHOICES[parser_choice]
            if not parser.applies_to_path(path):
                logger.warning(
                    f"Manually applying parser '{parser_choice}' to dependencies: {path}"
                )
        else:
            choice_and_parser = first_applicable_parser(path)
            if choice_and_parser is None:  # nothing found
                raise UnparseablePathException(
                    ctx="Parsing given dependencies path isn't supported", path=path
                )
            parser = choice_and_parser[1]
        yield from parser.execute(path.read_text(), Location(path))
    elif path.is_dir():
        logger.debug("Extracting dependencies from files under %s", path)
        for file in walk_dir(path):
            choice_and_parser = first_applicable_parser(file)
            if choice_and_parser is None:  # nothing found
                continue
            if parser_choice is None or choice_and_parser[0] == parser_choice:
                logger.debug(f"Extracting dependencies: {file}")
                yield from choice_and_parser[1].execute(
                    file.read_text(), Location(file)
                )
    else:
        raise UnparseablePathException(
            ctx="Dependencies declaration path is neither dir nor file", path=path
        )
