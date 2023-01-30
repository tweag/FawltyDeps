"""Parse Python source code and extract import statements."""

import ast
import json
import logging
import sys
from pathlib import Path
from typing import Iterator

import isort

from fawltydeps.types import Location, ParsedImport, PathOrSpecial
from fawltydeps.utils import walk_dir

logger = logging.getLogger(__name__)

ISORT_CONFIG = isort.Config(py_version="all")


class ArgParseError(Exception):
    """Indicate errors while parsing command-line arguments"""

    def __init__(self, msg: str):
        self.msg = msg


def parse_code(code: str, *, source: Location) -> Iterator[ParsedImport]:
    """Extract import statements from a string containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the code.
    """

    def is_external_import(name: str) -> bool:
        return isort.place_module(name, config=ISORT_CONFIG) == "THIRDPARTY"

    for node in ast.walk(ast.parse(code, filename=str(source.path))):
        if isinstance(node, ast.Import):
            logger.debug(ast.dump(node))
            for alias in node.names:
                name = alias.name.split(".", 1)[0]
                if is_external_import(name):
                    yield ParsedImport(
                        name=name, source=source.supply(lineno=node.lineno)
                    )
        elif isinstance(node, ast.ImportFrom):
            logger.debug(ast.dump(node))
            # Relative imports are always relative to the current package, and
            # will therefore not resolve to a third-party package.
            # They are therefore uninteresting to us.
            if node.level == 0 and node.module is not None:
                name = node.module.split(".", 1)[0]
                if is_external_import(name):
                    yield ParsedImport(
                        name=name, source=source.supply(lineno=node.lineno)
                    )


def parse_notebook_file(path: Path) -> Iterator[ParsedImport]:
    """Extract import statements from an ipynb notebook.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the file.
    """

    def remove_magic_command(line: str, source: Location) -> str:
        """Remove magic notebook commands from the given line."""
        if line.lstrip().startswith(("!", "%")):
            logger.warning(f"Found magic command {line!r} at {source}")
            return "\n"
        return line

    with path.open("rb") as notebook:
        notebook_content = json.load(notebook, strict=False)
    language_name = (
        notebook_content.get("metadata", {}).get("language_info", {}).get("name", "")
    )

    if language_name.lower() == "python":
        for cellno, cell in enumerate(notebook_content["cells"], start=1):
            source = Location(path, cellno)
            try:
                if cell["cell_type"] == "code":
                    lines = [
                        remove_magic_command(line, source.supply(lineno=n))
                        for n, line in enumerate(cell["source"], start=1)
                    ]
                    yield from parse_code("".join(lines), source=source)
            except Exception as exc:
                raise SyntaxError(f"Cannot parse code from {source}.") from exc

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
    yield from parse_code(path.read_text(), source=Location(path))


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


def parse_any_arg(arg: PathOrSpecial) -> Iterator[ParsedImport]:
    """Interpret the given command-line argument and invoke a suitable parser.

    These cases are handled:
      - arg == "-": Read code from stdin and pass to parse_code()
      - arg refers to a file: Call parse_python_file() or parse_notebook_file()
      - arg refers to a dir: Call parse_dir()

    Otherwise raise ArgParseError with a suitable error message.
    """
    if arg == "<stdin>":
        logger.info("Parsing Python code from standard input")
        return parse_code(sys.stdin.read(), source=Location(arg))
    assert isinstance(arg, Path)
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
