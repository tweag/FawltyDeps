"Parse imports from the source code"

import ast
import logging
from typing import Iterator

logger = logging.getLogger(__name__)


def parse_imports(code: str) -> Iterator[str]:
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            logger.debug(ast.dump(node, indent=4))
            for alias in node.names:
                yield alias.name
