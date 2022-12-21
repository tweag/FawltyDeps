"Collect declared dependencies of the project"
import logging
import os
from pathlib import Path
from typing import Iterator, Tuple

from pkg_resources import parse_requirements

logger = logging.getLogger(__name__)


def parse_requirements_contents(
    text: str, path_hint: Path
) -> Iterator[Tuple[str, Path]]:
    """
    Extract dependencies (packages names) from the requirement.txt file
    and other following Requirements File Format. For more information, see
    https://pip.pypa.io/en/stable/reference/requirements-file-format/.
    """
    for requirement in parse_requirements(text):
        yield (requirement.key, path_hint)


def extract_dependencies(path: Path) -> Iterator[Tuple[str, Path]]:
    """
    Extract dependencies from supported file types.
    Traverse directory tree to find matching files.
    Call handlers for each file type to extract dependencies.
    """
    parsers = {
        "requirements.txt": parse_requirements_contents,
        "requirements.in": parse_requirements_contents,
    }
    # TODO extract dependencies from setup.py
    # TODO extract dependencies from pyproject.toml

    for root, _dirs, files in os.walk(path):
        for filename in files:
            if filename in parsers:
                parser = parsers[filename]
                current_path = Path(root, filename)
                logger.debug(f"Extracting dependency from {current_path}.")
                yield from parser(current_path.read_text(), path_hint=current_path)
