"""Parse Python source code and extract import statements."""

import ast
import logging
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
