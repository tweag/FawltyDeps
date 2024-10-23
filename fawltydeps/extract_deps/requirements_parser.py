"""Code for parsing pip-style requirements and requirements files."""

import logging
from pathlib import Path
from typing import Iterator

from packaging.requirements import Requirement
from pip_requirements_parser import RequirementsFile  # type: ignore[import-untyped]

from fawltydeps.types import DeclaredDependency, Location

logger = logging.getLogger(__name__)


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
