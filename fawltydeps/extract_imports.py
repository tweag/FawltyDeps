"""Parse Python source code and extract import statements."""

import ast
import json
import logging
import os
import sys
from pathlib import Path
from typing import Iterator, Optional

from fawltydeps.types import ParsedImport

logger = logging.getLogger(__name__)


def parse_code(
    code: str, *, path_hint: Optional[Path] = None
) -> Iterator[ParsedImport]:
    """Extract import statements from a string containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the code.
    """
    filename = "<unknown>" if path_hint is None else str(path_hint)
    for node in ast.walk(ast.parse(code, filename=filename)):
        if isinstance(node, ast.Import):
            logger.debug(ast.dump(node))
            for alias in node.names:
                yield ParsedImport(
                    name=alias.name.split(".", 1)[0],
                    location=path_hint,
                    lineno=node.lineno,
                )
        elif isinstance(node, ast.ImportFrom):
            logger.debug(ast.dump(node))
            # Relative imports are always relative to the current package, and
            # will therefore not resolve to a third-party package.
            # They are therefore uninteresting to us.
            if node.level == 0 and node.module is not None:
                yield ParsedImport(
                    name=node.module.split(".", 1)[0],
                    location=path_hint,
                    lineno=node.lineno,
                )


def parse_notebook(path: Path) -> Iterator[ParsedImport]:
    """Extract import statements from an ipynb notebooke.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the file.
    """
    notebook_content = json.loads(path.read_text(), strict=False)
    for cell_index, cell in enumerate(notebook_content["cells"]):
        try:
            if cell["cell_type"] == "code":
                yield from parse_code("".join(cell["source"]), path_hint=path)
        except Exception as exc:
            raise SyntaxError(
                f"Cannot parse code from {path}: cell {cell_index}."
            ) from exc


def parse_file(path: Path) -> Iterator[ParsedImport]:
    """Extract import statements from a file containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the file.
    """
    yield from parse_code(path.read_text(), path_hint=path)


def parse_dir(path: Path) -> Iterator[ParsedImport]:
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
            elif path.suffix == ".ipynb":
                yield from parse_notebook(path)


class ParseError(Exception):
    """Indicate errors while parsing command-line arguments"""

    def __init__(self, msg: str):
        self.msg = msg


def parse_any_arg(arg: Path) -> Iterator[ParsedImport]:
    """Interpret the given command-line argument and invoke a suitable parser.

    These cases are handled:
      - arg == "-": Read code from stdin and pass to parse_code()
      - arg refers to a file: Call parse_file()
      - arg refers to a dir: Call parse_dir()

    Otherwise raise ParseError with a suitable error message.
    """
    if arg == Path("-"):
        logger.info("Parsing Python code from standard input")
        return parse_code(sys.stdin.read(), path_hint=Path("<stdin>"))
    if arg.is_file():
        logger.info("Parsing Python file %s", arg)
        return parse_file(arg)
    if arg.is_dir():
        logger.info("Parsing Python files under %s", arg)
        return parse_dir(arg)
    raise ParseError(f"Cannot parse code from {arg}: Not a dir or file!")
