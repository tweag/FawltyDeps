"Collect declared dependencies of the project"
import logging
import os
from pathlib import Path
from typing import Iterator, Tuple

from pkg_resources import parse_requirements

logger = logging.getLogger(__name__)


def extract_from_requirements_file(
    text: str, path_hint: Path
) -> Iterator[Tuple[str, Path]]:
    """
    Extract dependencies (packages names) from the requirement.txt file
    and other following Requirements File Format. For more information, see
    https://pip.pypa.io/en/stable/reference/requirements-file-format/.
    """
    for requirement in parse_requirements(text):
        yield (requirement.key, path_hint)


def extract_from_requirements(path: Path) -> Iterator[Tuple[str, Path]]:
    """
    Search for "requirements.txt" files in the project.

    Generates list of files matching the above criteria.
    """
    expected_filename = "requirements.txt"
    for root, _dirs, files in os.walk(path):
        for filename in files:
            current_path = Path(root, filename)
            if filename == expected_filename:
                logger.debug(f"Extracting dependency from {current_path}.")
                yield from extract_from_requirements_file(
                    text=current_path.read_text(), path_hint=current_path
                )


def extract_dependencies(path: Path) -> Iterator[Tuple[str, Path]]:
    """Extract dependencies from supported file types"""

    logger.debug("Extracting dependencies from requirements")
    yield from extract_from_requirements(path)

    # TODO extract dependencies from setup.py
    # TODO extract dependencies from pyproject.toml
