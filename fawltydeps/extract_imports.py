"""Parse Python source code and extract import statements."""

import ast
import logging
import os
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


def parse_code(code: str) -> Iterator[str]:
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            logger.debug(ast.dump(node))
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            logger.debug(ast.dump(node))
            yield node.module


def parse_file(path: Path) -> Iterator[str]:
    yield from parse_code(path.read_text())


def parse_dir(path: Path) -> Iterator[str]:
    for root, _dirs, files in os.walk(path):
        for filename in files:
            path = Path(root, filename)
            if path.suffix == ".py":
                yield from parse_file(path)
