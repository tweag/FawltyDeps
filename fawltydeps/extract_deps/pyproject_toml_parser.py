"""Code for parsing dependencies in various formats from pyproject.toml files."""

import contextlib
import logging
import sys
from pathlib import Path
from typing import Callable, Iterable, Iterator, Tuple

from fawltydeps.types import DeclaredDependency, Location, TomlData

from .requirements_parser import parse_one_req, parse_requirements_txt

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

logger = logging.getLogger(__name__)

ERROR_MESSAGE_TEMPLATE = "Failed to %s %s %s dependencies in %s: %s"

NamedLocations = Iterator[Tuple[str, Location]]


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


def parse_pep735_pyproject_contents(
    parsed_contents: TomlData, source: Location
) -> Iterator[DeclaredDependency]:
    """Extract dependencies from a pyproject.toml using PEP 735 dependency groups."""

    def parse_dep_groups(contents: TomlData, src: Location) -> NamedLocations:
        for group in contents["dependency-groups"].values():
            for req in group:
                if isinstance(req, dict) and len(req) == 1 and "include-group" in req:
                    # This include refers to another dependency group. At this
                    # time we don't differentiate between which group
                    # dependencies come from, nor do we care how many times
                    # a dependency is mentioned/included. Therefore, we can
                    # simply assume that the group being referenced here will
                    # be parsed/handled on its own, and we don't need to take
                    # steps to find/yield the same deps from here.
                    pass
                else:
                    yield req, src

    fields_parsers = [("dependency-groups", parse_dep_groups)]

    yield from parse_pyproject_elements(
        parsed_contents, source, "PEP735", fields_parsers
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

    for dep in parse_pep735_pyproject_contents(parsed_contents, source):
        yield dep

    if "poetry" in parsed_contents.get("tool", {}):
        yield from parse_poetry_pyproject_dependencies(
            parsed_contents["tool"]["poetry"], source
        )
    else:
        logger.debug("%s does not contain [tool.poetry].", source)
