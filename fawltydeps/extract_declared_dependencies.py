"""Collect declared dependencies of the project"""

import ast
import configparser
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterator

from pkg_resources import Requirement

from fawltydeps.limited_eval import CannotResolve, VariableTracker
from fawltydeps.types import ArgParseError, DeclaredDependency, Location
from fawltydeps.utils import walk_dir

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=E1101
else:
    import tomli as tomllib

TomlData = Dict[str, Any]  # type: ignore

logger = logging.getLogger(__name__)

ERROR_MESSAGE_TEMPLATE = "Failed to %s %s %s dependencies in %s."


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
        if not line or line.lstrip().startswith(("-", "#")):
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

    def parse_main_dependencies(
        poetry_config: TomlData, source: Location
    ) -> Iterator[DeclaredDependency]:
        for requirement in poetry_config["dependencies"].keys():
            if requirement != "python":
                yield parse_one_req(requirement, source)

    def parse_group_dependencies(
        poetry_config: TomlData, source: Location
    ) -> Iterator[DeclaredDependency]:
        for group in poetry_config["group"].values():
            for requirement in group["dependencies"].keys():
                if requirement != "python":
                    yield parse_one_req(requirement, source)

    def parse_extra_dependencies(
        poetry_config: TomlData, source: Location
    ) -> Iterator[DeclaredDependency]:
        for group in poetry_config["extras"].values():
            if isinstance(group, list):
                for requirement in group:
                    yield parse_one_req(requirement, source)
            else:
                raise TypeError(f"{group!r} is of type {type(group)}. Expected a list.")

    fields_parsers = {
        "main": parse_main_dependencies,
        "group": parse_group_dependencies,
        "extra": parse_extra_dependencies,
    }

    for field_type, parser in fields_parsers.items():
        try:
            yield from parser(poetry_config, source)
        except KeyError:  # missing fields:
            logger.debug(
                ERROR_MESSAGE_TEMPLATE,
                "find",
                "Poetry",
                field_type,
                source,
            )
        except (AttributeError, TypeError):  # invalid config
            logger.error(
                ERROR_MESSAGE_TEMPLATE,
                "parse",
                "Poetry",
                field_type,
                source,
            )


def parse_pep621_pyproject_contents(
    parsed_contents: TomlData, source: Location
) -> Iterator[DeclaredDependency]:
    """Extract dependencies from a pyproject.toml using the PEP 621 fields."""

    def parse_main_dependencies(
        parsed_contents: TomlData, source: Location
    ) -> Iterator[DeclaredDependency]:
        dependencies = parsed_contents["project"]["dependencies"]
        if isinstance(dependencies, list):
            for requirement in dependencies:
                yield parse_one_req(requirement, source)
        else:
            raise TypeError(
                f"{dependencies!r} of type {type(dependencies)}. Expected list."
            )

    def parse_optional_dependencies(
        parsed_contents: TomlData, source: Location
    ) -> Iterator[DeclaredDependency]:
        for group in parsed_contents["project"]["optional-dependencies"].values():
            for requirement in group:
                yield parse_one_req(requirement, source)

    fields_parsers = {
        "main": parse_main_dependencies,
        "optional": parse_optional_dependencies,
    }
    for field_type, parser in fields_parsers.items():
        try:
            yield from parser(parsed_contents, source)
        except KeyError:
            logger.debug(ERROR_MESSAGE_TEMPLATE, "find", "PEP621", field_type, source)
        except (AttributeError, TypeError):
            logger.error(ERROR_MESSAGE_TEMPLATE, "parse", "PEP621", field_type, source)


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
        logger.debug("%s does not contain [tool.poetry].")


def extract_declared_dependencies(path: Path) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from supported file types.

    Pass a file to parse dependency declarations found inside that file. Pass
    a directory to traverse that directory tree to find and automatically parse
    any supported files.

    Generate (i.e. yield) a DeclaredDependency object for each dependency found.
    There is no guaranteed ordering on the generated dependencies.
    """
    parsers = {
        "requirements.txt": parse_requirements_contents,
        "requirements-all.txt": parse_requirements_contents,
        "requirements.in": parse_requirements_contents,
        "setup.py": parse_setup_contents,
        "setup.cfg": parse_setup_cfg_contents,
        "pyproject.toml": parse_pyproject_contents,
    }

    def parse_dependencies_in_file(path: Path) -> Iterator[DeclaredDependency]:
        if path.name in parsers:
            parser = parsers[path.name]
            logger.debug(f"Extracting dependencies from {path}.")
            yield from parser(path.read_text(), source=Location(path))

    logger.debug(path)

    if path.is_file():
        if not path.name in parsers:
            raise ArgParseError(f"Parsing file {path.name} is not supported")
        yield from parse_dependencies_in_file(path)

    else:
        for file in walk_dir(path):
            yield from parse_dependencies_in_file(file)
