"""Code for parsing dependencies from environment.yml files."""

import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Union

from fawltydeps.types import DeclaredDependency, Location

from .requirements_parser import parse_one_req

logger = logging.getLogger(__name__)

YamlDependencyData = Union[List[str], Dict[str, "YamlDependencyData"], Any, None]  # type: ignore[misc]


class InvalidCondaRequirement(ValueError):  # noqa: N818
    """Invalid Conda dependency specifier.

    Modeled on packaging.requirements.InvalidRequirement.
    """


def parse_one_conda_dep(req_str: str, source: Location) -> DeclaredDependency:
    """Parse a single Conda dependency string.

    Simplified from the Conda's own MatchSpec parser at:
    https://github.com/conda/conda/blob/aa0fb6f3ae6/conda/models/match_spec.py#L85
    For now, we're only interested in the Conda package name.
    """
    if "::" in req_str:  # remove channel/subdir from front
        _, req_str = req_str.split("::", 1)
    if "[" in req_str:  # remove bracket stuff from back
        req_str, _ = req_str.split("[]", 1)
    # package name comes before version/build info, which starts with one of "><!=~ "
    name_match = re.match(r"[^ =<>!~]+", req_str)
    if not name_match:
        raise InvalidCondaRequirement(
            f"Expected package name at the start of dependency specifier: {req_str!r}"
        )
    return DeclaredDependency(name_match.group(0), source)


def parse_environment_yml_deps(
    parsed_deps: YamlDependencyData,
    source: Location,
    context_name: str,
    parse_item: Callable[[str, Location], DeclaredDependency],
) -> Iterator[DeclaredDependency]:
    """Use the given `dependencies:` data from environment.yml to collect dependencies."""
    debug_msg = f"Failed to find {context_name} dependencies in {source}."
    error_msg = f"Failed to parse {context_name} dependencies in {source}:"

    if parsed_deps is None:
        logger.debug(debug_msg)
        return
    elif not isinstance(parsed_deps, list):
        logger.error(f"{error_msg} Not a sequence: {parsed_deps!r}")
        return
    for dep_item in parsed_deps:
        if isinstance(dep_item, str):
            try:
                yield parse_item(dep_item, source)
            except ValueError as e:
                # InvalidCondaRequirement or packaging.requirements.InvalidRequirement
                logger.error(f"{error_msg} {e}")
        elif isinstance(dep_item, dict) and len(dep_item) == 1 and "pip" in dep_item:
            pip_deps = dep_item.get("pip")
            yield from parse_environment_yml_deps(
                pip_deps, source, "Pip", parse_one_req
            )
        else:
            logger.error(f"{error_msg} Not a string: {dep_item!r}")
            continue


def parse_environment_yml(path: Path) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from environment.yml."""
    import yaml

    source = Location(path)
    skip = {"python"}

    with path.open() as f:
        try:
            parsed_data = yaml.safe_load(f)
        except (yaml.parser.ParserError, yaml.scanner.ScannerError) as e:
            logger.error(f"Failed to parse {source}: {e}")
            return
        if not isinstance(parsed_data, dict):
            logger.error(f"Failed to parse {source}: No top-level mapping found!")
            return

    for dep in parse_environment_yml_deps(
        parsed_data.get("dependencies"), source, "Conda", parse_one_conda_dep
    ):
        if dep.name not in skip:
            yield dep
