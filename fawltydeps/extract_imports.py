"""Parse Python source code and extract import statements."""

import ast
import logging
import os
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


def parse_code(code: str, *, path_hint: Optional[Path] = None) -> Iterator[str]:
    """Extract import statements from a string containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the code.
    """
    filename = "<unknown>" if path_hint is None else str(path_hint)
    for node in ast.walk(ast.parse(code, filename=filename)):
        if isinstance(node, ast.Import):
            logger.debug(ast.dump(node))
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            logger.debug(ast.dump(node))
            yield node.module


def parse_file(path: Path) -> Iterator[str]:
    """Extract import statements from a file containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the file.
    """
    yield from parse_code(path.read_text(), path_hint=path)


def parse_dir(path: Path) -> Iterator[str]:
    """Extract import statements Python files in the given directory.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the file. Modules that are imported by several files will
    be yielded multiple times.
    """
    for root, _dirs, files in os.walk(path):
        for filename in files:
            path = Path(root, filename)
            if path.suffix == ".py":
                yield from parse_file(path)
