"""Collect declared dependencies of the project"""

import ast
import configparser
import logging
import re
import sys
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, NamedTuple, Optional, Tuple

from more_itertools import split_at
from pkg_resources import Requirement

from fawltydeps.limited_eval import CannotResolve, VariableTracker
from fawltydeps.types import DeclaredDependency, Location, UnparseablePathException
from fawltydeps.utils import walk_dir

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=E1101
else:
    import tomli as tomllib

TomlData = Dict[str, Any]  # type: ignore

logger = logging.getLogger(__name__)

ERROR_MESSAGE_TEMPLATE = "Failed to %s %s %s dependencies in %s: %s"
PER_REQUIREMENT_OPTIONS = [
    "--install-option",
    "--global-option",
    "config-setting",
    "--hash",
]

NamedLocations = Iterator[Tuple[str, Location]]
IterDeps = Iterator[DeclaredDependency]


class DependencyParsingError(Exception):
    """Error raised when parsing of dependency fails"""

    def __init__(self, node: ast.AST):
        super().__init__(node)
        self.node = node


def parse_one_req(req_text: str, source: Location) -> DeclaredDependency:
    """Returns the name of a dependency declared in a requirement specifier."""
    req = Requirement.parse(req_text)
    req_name = req.unsafe_name
    return DeclaredDependency(req_name, source)


def parse_requirements_contents(text: str, source: Location) -> IterDeps:
    """Extract dependencies (packages names) from a requirements file.

    This is usually a requirements.txt file or any other file following the
    Requirements File Format as documented here:
    https://pip.pypa.io/en/stable/reference/requirements-file-format/.
    """
    parse_one = partial(parse_one_req, source=source)
    for line in text.splitlines():
        cleaned = line.lstrip()
        if (
            not cleaned  # skip empty lines
            or cleaned.startswith(("-", "#"))  # skip options and comments
            or ("://" in line.split()[0])  # skip bare URLs at the start of line
        ):
            continue
        try:
            yield parse_one(line)
        except ValueError:
            sep = " "
            fields = line.split(sep)
            splits = list(
                split_at(
                    fields,
                    lambda s: s.startswith("--"),
                    maxsplit=1,
                    keep_separator=True,
                )
            )
            if len(splits) == 3:  # pre, sep, post
                pre_break, breakpoints, _ = splits
                assert 1 == len(breakpoints)
                if [
                    per_req_opt
                    for per_req_opt in PER_REQUIREMENT_OPTIONS
                    if breakpoints[0].startswith(per_req_opt)
                ]:
                    # https://pip.pypa.io/en/stable/reference/requirements-file-format/#per-requirement-options
                    new_req_try = sep.join(pre_break)
                    yield parse_one(new_req_try)
                else:
                    raise
            else:
                raise  # can't rescue the parse


def parse_setup_contents(text: str, source: Location) -> IterDeps:
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

    def _extract_deps_from_setup_call(node: ast.Call) -> IterDeps:
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


def parse_setup_cfg_contents(text: str, source: Location) -> IterDeps:
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

    def parse_value(value: str) -> IterDeps:
        yield from parse_requirements_contents(value, source=source)

    def extract_section(section: str) -> IterDeps:
        if section in parser:
            for option in parser.options(section):
                value = parser.get(section, option)
                logger.debug("Dependencies found in [%s]: %s", section, value)
                yield from parse_value(value)

    def extract_option_from_section(section: str, option: str) -> IterDeps:
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
) -> IterDeps:
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
) -> IterDeps:
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
) -> IterDeps:
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


def parse_pyproject_contents(text: str, source: Location) -> IterDeps:
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


Parse = Callable[[str, Location], IterDeps]


class ParsingStrategy(NamedTuple):
    """Named pairing of an applicability criterion and a dependency parser"""

    applies_to_path: Callable[[Path], bool]
    execute: Parse


class ParserChoice(Enum):
    """Enumerate the choices of dependency declaration parsers."""

    REQUIREMENTS_TXT = ParsingStrategy(
        lambda path: re.compile(r".*\brequirements\b.*\.(txt|in)").match(path.name)
        is not None,
        parse_requirements_contents,
    )
    SETUP_PY = ParsingStrategy(
        lambda path: path.name == "setup.py", parse_setup_contents
    )
    SETUP_CFG = ParsingStrategy(
        lambda path: path.name == "setup.cfg", parse_setup_cfg_contents
    )
    PYPROJECT_TOML = ParsingStrategy(
        lambda path: path.name == "pyproject.toml", parse_pyproject_contents
    )

    def to_cmdl(self) -> str:
        """Represent this value as a command-line arg choice."""
        return self.name.lower().replace("_", ".")

    @classmethod
    def from_cmdl(cls, arg: str) -> Optional["ParserChoice"]:
        """Attempt to parse a value from a command-line argument."""
        query = arg.upper().replace(".", "_")
        try:
            return next(choice for choice in cls if choice.name == query)
        except StopIteration:
            return None


def finalize_parse_strategy(
    path: Path, parser_choice: Optional[ParserChoice] = None
) -> Optional[Parse]:
    """Use the given parser choice and path to parse to determine how to do the parse."""
    if parser_choice is None:
        try:
            strategy = next(
                pc.value for pc in ParserChoice if pc.value.applies_to_path(path)
            )
        except StopIteration:
            return None
    else:
        strategy = parser_choice.value
        if not strategy.applies_to_path(path):
            logger.info(
                f"Manually applying parsing strategy {parser_choice.name}, "
                f"which doesn't automatically apply to given path: {path}"
            )
    return strategy.execute


def extract_declared_dependencies(
    path: Path, parser_choice: Optional[ParserChoice] = None
) -> IterDeps:
    """Extract dependencies (package names) from supported file types.

    Pass a path from which to discover and parse dependency declarations. Pass
    a directory to traverse that directory tree to find and automatically parse
    any supported files.

    Generate (i.e. yield) a DeclaredDependency object for each dependency found.
    There is no guaranteed ordering on the generated dependencies.
    """

    logger.debug(f"Entered extract_declared_dependencies given path: {path}")

    get_parser = partial(finalize_parse_strategy, parser_choice=parser_choice)

    if path.is_file():
        parse = get_parser(path)
        if parse is None:
            raise UnparseablePathException(
                ctx="Parsing given deps path isn't supported", path=path
            )
        logger.debug(f"Extracting dependencies from {path}.")
        yield from parse(path.read_text(), Location(path))
    elif path.is_dir():
        logger.debug("Extracting dependencies from files under %s", path)
        for file in walk_dir(path):
            parse = get_parser(file)
            if parse:
                logger.debug(f"Extracting dependencies from {file}.")
                yield from parse(file.read_text(), Location(file))
    else:
        raise UnparseablePathException(
            ctx="Dependencies declaration path is neither dir nor file", path=path
        )
