"""Collect declared dependencies of the project."""

import ast
import configparser
import contextlib
import logging
import re
import sys
import tokenize
from dataclasses import replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, Iterable, Iterator, NamedTuple, Optional, Tuple, Union

from packaging.requirements import Requirement
from pip_requirements_parser import RequirementsFile  # type: ignore[import]

from fawltydeps.limited_eval import CannotResolve, VariableTracker
from fawltydeps.settings import ParserChoice
from fawltydeps.types import (
    DeclaredDependency,
    DepsSource,
    Location,
    TomlData,
    UnparseablePathError,
)

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

logger = logging.getLogger(__name__)

ERROR_MESSAGE_TEMPLATE = "Failed to %s %s %s dependencies in %s: %s"

NamedLocations = Iterator[Tuple[str, Location]]


class DependencyParsingError(Exception):
    """Error raised when parsing of dependency fails."""

    def __init__(self, node: ast.AST):
        super().__init__(node)
        self.node = node


def parse_one_req(req_text: str, source: Location) -> DeclaredDependency:
    """Return the name of a dependency declared in a requirement specifier."""
    return DeclaredDependency(Requirement(req_text).name, source)


def parse_requirements_txt(path: Path) -> Iterator[DeclaredDependency]:
    """Extract dependencies (packages names) from a requirements file.

    This is usually a requirements.txt file or any other file following the
    Requirements File Format as documented here:
    https://pip.pypa.io/en/stable/reference/requirements-file-format/.
    """
    source = Location(path)
    parsed = RequirementsFile.from_file(path)
    for dep in parsed.requirements:
        if dep.name:
            yield DeclaredDependency(dep.name, source)

    if parsed.invalid_lines and logger.isEnabledFor(logging.DEBUG):
        error_messages = "\n".join(line.dumps() for line in parsed.invalid_lines)
        logger.debug(f"Invalid lines found in {source}:\n{error_messages}")


def parse_setup_py(path: Path) -> Iterator[DeclaredDependency]:  # noqa: C901
    """Extract dependencies (package names) from setup.py.

    This file can contain arbitrary Python code, and simply executing it has
    potential security implications. For now, we parse it with the `ast` module,
    looking for the first call to a `setup()` function, and attempt to extract
    the `install_requires` and `extras_require` keyword args from that function
    call.
    """
    source = Location(path)
    # Attempt to keep track of simple variable assignments (name -> value)
    # declared in the setup.py prior to the setup() call, so that we can
    # resolve any variable references in the arguments to the setup() call.
    tracked_vars = VariableTracker(source)

    def _extract_deps_from_value(
        value: Union[str, Iterable[str]],
        node: ast.AST,
    ) -> Iterator[DeclaredDependency]:
        if isinstance(value, str):  # expected list, but got string
            value = [value]  # parse as if a single-element list is given
        try:
            for item in value:
                yield parse_one_req(item, source)
        except ValueError as e:  # parse_one_req() failed
            raise DependencyParsingError(node) from e

    def _extract_deps_from_setup_call(
        node: ast.Call,
    ) -> Iterator[DeclaredDependency]:
        for keyword in node.keywords:
            try:
                if keyword.arg == "install_requires":
                    value = tracked_vars.resolve(keyword.value)
                    yield from _extract_deps_from_value(value, keyword.value)
                elif keyword.arg == "extras_require":
                    value = tracked_vars.resolve(keyword.value)
                    if not isinstance(value, dict):
                        raise DependencyParsingError(keyword.value)
                    for items in value.values():
                        yield from _extract_deps_from_value(items, keyword.value)
            except (DependencyParsingError, CannotResolve) as exc:
                if sys.version_info >= (3, 9):
                    unparsed_content = ast.unparse(exc.node)
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

    with tokenize.open(path) as setup_py:
        setup_contents = ast.parse(setup_py.read(), filename=str(source.path))
    for node in ast.walk(setup_contents):
        tracked_vars.evaluate(node)
        if _is_setup_function_call(node):
            # Below line is not checked by mypy, but `_is_setup_function_call`
            # makes sure that `node` is of a proper type.
            yield from _extract_deps_from_setup_call(node.value)  # type: ignore[attr-defined]
            break


def parse_setup_cfg(path: Path) -> Iterator[DeclaredDependency]:
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
    source = Location(path)
    parser = configparser.ConfigParser()
    try:
        parser.read([path])
    except configparser.Error as exc:
        logger.debug(exc)
        logger.error("Could not parse contents of `%s`", source)
        return

    def parse_value(value: str) -> Iterator[DeclaredDependency]:
        # Ugly hack since parse_requirements_txt() accepts only a path.
        # TODO: try leveraging RequirementsFile.from_string once
        #       pip-requirements-parser updates.
        # See:  https://github.com/nexB/pip-requirements-parser/pull/17

        # https://github.com/nexB/pip-requirements-parser/pull/19#discussion_r1379279880
        temp_file = NamedTemporaryFile(
            "wt",
            delete=False,
            # we prefer utf8 encoded strings, but ...
            # - must not change newlines
            # - must not  change encoding, fallback to system encoding for compatibility
            newline="",
            encoding=None,
        )
        temp_file.write(value)
        temp_file.close()
        try:
            for dep in parse_requirements_txt(Path(temp_file.name)):
                yield replace(dep, source=source)
        finally:
            Path(temp_file.name).unlink()

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
            (req, src)
            for req in contents["dependencies"].keys()  # noqa: SIM118
            if req != "python"
        )

    def parse_group(contents: TomlData, src: Location) -> NamedLocations:
        return (
            (req, src)
            for group in contents["group"].values()
            for req in group["dependencies"].keys()  # noqa: SIM118
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


def parse_pixi_pyproject_dependencies(
    pixi_config: TomlData, source: Location
) -> Iterator[DeclaredDependency]:
    """Extract dependencies from `tool.pixi` fields in a pyproject.toml.

    - [tool.pixi.dependencies] contains mandatory Conda deps
    - [tool.pixi.pypi-dependencies] contains mandatory PyPI deps
    - [tool.pixi.feature.<NAME>.dependencies] contains optional Conda deps
    - [tool.pixi.feature.<NAME>.pypi-dependencies] contains optional PyPI deps

    NOTE: We do not currently differentiate between Conda dependencies and PyPI
    dependencies, meaning that we assume that a Conda dependency named FOO will
    map one-to-one to a Python package named FOO. This is certainly not true for
    Conda dependencies that are not Python packages, and it probably isn't even
    true for all Conda dependencies that do indeed include Python packages.
    """

    def parse_main(contents: TomlData, src: Location) -> NamedLocations:
        return (
            (req, src)
            for req in contents["dependencies"].keys()  # noqa: SIM118
            if req != "python"
        )

    def parse_pypi(contents: TomlData, src: Location) -> NamedLocations:
        return (
            (req, src)
            for req in contents["pypi-dependencies"].keys()  # noqa: SIM118
        )

    def parse_feature(contents: TomlData, src: Location) -> NamedLocations:
        return (
            (req, src)
            for feature in contents["feature"].values()
            for req in feature.get("dependencies", {}).keys()  # noqa: SIM118
            if req != "python"
        )

    def parse_feature_pypi(contents: TomlData, src: Location) -> NamedLocations:
        return (
            (req, src)
            for feature in contents["feature"].values()
            for req in feature.get("pypi-dependencies", {}).keys()  # noqa: SIM118
        )

    fields_parsers = [
        ("main", parse_main),
        ("pypi", parse_pypi),
        ("feature", parse_feature),
        ("feature pypi", parse_feature_pypi),
    ]
    yield from parse_pyproject_elements(pixi_config, source, "Pixi", fields_parsers)


def parse_pep621_pyproject_contents(  # noqa: C901
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

    if "dynamic" in parsed_contents.get("project", {}):
        yield from parse_dynamic_pyproject_contents(parsed_contents, source)
        if "dependencies" in parsed_contents["project"]["dynamic"]:
            if "optional-dependencies" in parsed_contents["project"]["dynamic"]:
                fields_parsers = []
            else:
                fields_parsers = [("optional", parse_optional)]
        elif "optional-dependencies" in parsed_contents["project"]["dynamic"]:
            fields_parsers = [("main", parse_main)]

    yield from parse_pyproject_elements(
        parsed_contents, source, "PEP621", fields_parsers
    )


def parse_dynamic_pyproject_contents(
    parsed_contents: TomlData, source: Location
) -> Iterator[DeclaredDependency]:
    """Extract dynamic dependencies from a pyproject.toml using the PEP 621 fields."""
    dynamic = parsed_contents["project"]["dynamic"]

    deps_files = []
    try:
        if "dependencies" in dynamic:
            deps_files = parsed_contents["tool"]["setuptools"]["dynamic"][
                "dependencies"
            ]["file"]
    except KeyError:
        pass

    optional_deps_files = []
    try:
        if "optional-dependencies" in dynamic:
            optional_deps = parsed_contents["tool"]["setuptools"]["dynamic"][
                "optional-dependencies"
            ]
            # Extract the file paths and flatten them into a single list
            optional_deps_files = [
                file_path
                for file_path_list in [v["file"] for v in optional_deps.values()]
                for file_path in file_path_list
            ]
    except KeyError:
        pass

    dynamic_files = deps_files + optional_deps_files
    for req_file in dynamic_files:
        req_file_path = Path(source.path).parent / req_file
        if req_file_path.exists():
            yield from parse_requirements_txt(req_file_path)
        else:
            logger.error("%s does not exist. Skipping.", req_file_path)


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


def parse_pyproject_toml(path: Path) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from pyproject.toml.

    There are multiple ways to declare dependencies inside a pyproject.toml.
    We currently handle:
    - PEP 621 core and dynamic metadata fields.
    - Poetry-specific metadata in `tool.poetry` sections.
    - Pixi-specific metadata in `tool.pixi` sections.
    """
    source = Location(path)
    with path.open("rb") as tomlfile:
        try:
            parsed_contents = tomllib.load(tomlfile)
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Failed to parse {source}: {e}")
            return

    skip = set()

    # Skip dependencies onto self (such as Pixi's "editable mode" hack)
    with contextlib.suppress(KeyError):
        skip.add(parsed_contents["project"]["name"])

    # In Pixi, dependencies from [tool.pixi.dependencies] _override_
    # dependencies from PEP621 dependencies with the same name.
    # Therefore, parse the Pixi sections first, and skip dependencies with the
    # same name in the PEP621 section below.
    if "pixi" in parsed_contents.get("tool", {}):
        for dep in parse_pixi_pyproject_dependencies(
            parsed_contents["tool"]["pixi"], source
        ):
            if dep.name not in skip:
                skip.add(dep.name)
                yield dep
    else:
        logger.debug("%s does not contain [tool.pixi].", source)

    for dep in parse_pep621_pyproject_contents(parsed_contents, source):
        if dep.name not in skip:
            yield dep

    if "poetry" in parsed_contents.get("tool", {}):
        yield from parse_poetry_pyproject_dependencies(
            parsed_contents["tool"]["poetry"], source
        )
    else:
        logger.debug("%s does not contain [tool.poetry].", source)


def parse_pixi_toml(path: Path) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from pixi.toml.

    See https://pixi.sh/latest/reference/project_configuration/ for more
    information about the pixi.toml format.
    """
    source = Location(path)
    with path.open("rb") as tomlfile:
        try:
            parsed_contents = tomllib.load(tomlfile)
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Failed to parse {source}: {e}")
            return

    skip = set()

    # Skip dependencies onto self (such as Pixi's "editable mode" hack)
    with contextlib.suppress(KeyError):
        skip.add(parsed_contents["project"]["name"])

    for dep in parse_pixi_pyproject_dependencies(parsed_contents, source):
        if dep.name not in skip:
            skip.add(dep.name)
            yield dep


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
