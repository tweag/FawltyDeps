"""Code for parsing dependencies from pixi.toml files."""

import contextlib
import logging
import sys
from pathlib import Path
from typing import Iterator

from fawltydeps.types import DeclaredDependency, Location

from .pyproject_toml_parser import parse_pixi_pyproject_dependencies

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

logger = logging.getLogger(__name__)


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
