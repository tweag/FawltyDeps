"""Parse Python source code and extract import statements."""

import ast
import json
import logging
import sys
from pathlib import Path
from typing import Iterable, Iterator

import isort

from fawltydeps.types import ArgParseError, Location, ParsedImport, PathOrSpecial
from fawltydeps.utils import walk_dir

logger = logging.getLogger(__name__)


def isort_config(path: Path) -> isort.Config:
    """Configure isort to correctly classify import statements.

    In order for isort to correctly differentiate between first- and third-party
    imports, we need to pass in a configuration object that tells isort where
    to look for first-party imports.
    """
    return isort.Config(
        directory=str(path),  # Resolve first-party imports from this directory
        py_version="all",  # Ignore stdlib imports from all stdlib versions
    )


ISORT_CONFIG = isort_config(Path("."))


def parse_code(code: str, *, source: Location) -> Iterator[ParsedImport]:
    """Extract import statements from a string containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the code.
    """

    def is_external_import(name: str) -> bool:
        return isort.place_module(name, config=ISORT_CONFIG) == "THIRDPARTY"

    try:
        parsed_code = ast.parse(code, filename=str(source.path))
    except SyntaxError as exc:
        logger.error(f"Could not parse code from {source}: {exc}")
        return
    for node in ast.walk(parsed_code):
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

    def filter_out_magic_commands(
        lines: Iterable[str], source: Location
    ) -> Iterator[str]:
        """Convert lines with magic notebook commands into empty lines."""
        command_continues = False
        for lineno, line in enumerate(lines, start=1):
            if line.lstrip().startswith(("!", "%")):
                logger.info(
                    f"Found magic command {line!r} at {source.supply(lineno=lineno)}"
                )
                command_continues = line.rstrip("\n").endswith("\\")
                yield "\n"
            elif command_continues:
                command_continues = line.rstrip("\n").endswith("\\")
                yield "\n"
            else:
                yield line

    with path.open("rb") as notebook:
        try:
            notebook_content = json.load(notebook, strict=False)
        except json.decoder.JSONDecodeError as exc:
            logger.error(f"Could not parse code from {path}: {exc}")
            return

    language_name = (
        notebook_content.get("metadata", {}).get("language_info", {}).get("name", "")
    )

    if language_name.lower() == "python":
        for cellno, cell in enumerate(notebook_content["cells"], start=1):
            source = Location(path, cellno)
            try:
                if cell["cell_type"] == "code":
                    lines = filter_out_magic_commands(cell["source"], source=source)
                    yield from parse_code("".join(lines), source=source)
            except KeyError as exc:
                logger.error(f"Could not parse code from {source}: {exc}.")

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
    global ISORT_CONFIG  # pylint: disable=global-statement
    old_config = ISORT_CONFIG
    ISORT_CONFIG = isort_config(path)
    try:
        for file in walk_dir(path):
            if file.suffix == ".py":
                yield from parse_python_file(file)
            elif file.suffix == ".ipynb":
                yield from parse_notebook_file(file)
    finally:
        ISORT_CONFIG = old_config


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
