"""Parse Python source code and extract import statements."""

import ast
import json
import logging
import sys
from pathlib import Path
from typing import Iterator, Optional

import isort

from fawltydeps.types import ParsedImport
from fawltydeps.utils import walk_dir

logger = logging.getLogger(__name__)


class ArgParseError(Exception):
    """Indicate errors while parsing command-line arguments"""

    def __init__(self, msg: str):
        self.msg = msg


def parse_code(
    code: str, *, path_hint: Optional[Path] = None, cellno: Optional[int] = None
) -> Iterator[ParsedImport]:
    """Extract import statements from a string containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the code.
    """

    def is_stdlib_import(name: str) -> bool:
        return isort.place_module(name) == "STDLIB"

    filename = "<unknown>" if path_hint is None else str(path_hint)
    for node in ast.walk(ast.parse(code, filename=filename)):
        if isinstance(node, ast.Import):
            logger.debug(ast.dump(node))
            for alias in node.names:
                name = alias.name.split(".", 1)[0]
                if not is_stdlib_import(name):
                    yield ParsedImport(
                        name=name,
                        location=path_hint,
                        lineno=node.lineno,
                        cellno=cellno,
                    )
        elif isinstance(node, ast.ImportFrom):
            logger.debug(ast.dump(node))
            # Relative imports are always relative to the current package, and
            # will therefore not resolve to a third-party package.
            # They are therefore uninteresting to us.
            if node.level == 0 and node.module is not None:
                name = node.module.split(".", 1)[0]
                if not is_stdlib_import(name):
                    yield ParsedImport(
                        name=name,
                        location=path_hint,
                        lineno=node.lineno,
                        cellno=cellno,
                    )


def parse_notebook_file(path: Path) -> Iterator[ParsedImport]:
    """Extract import statements from an ipynb notebook.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the file.
    """
    with path.open("rb") as notebook:
        notebook_content = json.load(notebook, strict=False)
    language_name = (
        notebook_content.get("metadata", {}).get("language_info", {}).get("name", "")
    )

    if language_name.lower() == "python":
        for cell_index, cell in enumerate(notebook_content["cells"]):
            try:
                if cell["cell_type"] == "code":
                    yield from parse_code(
                        "".join(cell["source"]), path_hint=path, cellno=cell_index
                    )
            except Exception as exc:
                raise SyntaxError(
                    f"Cannot parse code from {path}: cell {cell_index}."
                ) from exc
    elif not language_name:
        logger.info(
            f"Skipping the notebook on {path}. "
            "Could not find the programming language name in the notebook's metadata.",
        )
    else:
        logger.info(
            "FawltyDeps supports parsing Python notebooks. "
            f"Found {language_name} in the notebook's metadata on {path}.",
        )


def parse_python_file(path: Path) -> Iterator[ParsedImport]:
    """Extract import statements from a file containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the file.
    """
    yield from parse_code(path.read_text(), path_hint=path)


def parse_dir(path: Path) -> Iterator[ParsedImport]:
    """Extract import statements from Python files in the given directory.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in each file, but the order in which files are parsed is
    unspecified. Modules that are imported multiple times (in the same file or
    across several files) will be yielded multiple times.
    """
    for file in walk_dir(path):
        if file.suffix == ".py":
            yield from parse_python_file(file)
        elif file.suffix == ".ipynb":
            yield from parse_notebook_file(file)


def parse_any_arg(arg: Path) -> Iterator[ParsedImport]:
    """Interpret the given command-line argument and invoke a suitable parser.

    These cases are handled:
      - arg == "-": Read code from stdin and pass to parse_code()
      - arg refers to a file: Call parse_python_file() or parse_notebook_file()
      - arg refers to a dir: Call parse_dir()

    Otherwise raise ArgParseError with a suitable error message.
    """
    if arg == Path("-"):
        logger.info("Parsing Python code from standard input")
        return parse_code(sys.stdin.read(), path_hint=Path("<stdin>"))
    if arg.is_file():
        if arg.suffix == ".py":
            logger.info("Parsing Python file %s", arg)
            return parse_python_file(arg)
        if arg.suffix == ".ipynb":
            logger.info("Parsing Notebook file %s", arg)
            return parse_notebook_file(arg)
        raise ArgParseError(
            f"Cannot parse code from {arg}: supported formats are .py and .ipynb."
        )
    if arg.is_dir():
        logger.info("Parsing Python files under %s", arg)
        return parse_dir(arg)
    raise ArgParseError(f"Cannot parse code from {arg}: Not a dir or file!")
