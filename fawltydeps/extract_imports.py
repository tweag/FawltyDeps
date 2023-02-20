"""Parse Python source code and extract import statements."""

import ast
import json
import logging
import sys
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple

import isort

from fawltydeps.types import (
    Location,
    ParsedImport,
    PathOrSpecial,
    UnparseablePathException,
)
from fawltydeps.utils import dirs_between, walk_dir

logger = logging.getLogger(__name__)


def make_isort_config(path: Path, src_paths: Tuple[Path, ...] = ()) -> isort.Config:
    """Configure isort to correctly classify import statements.

    In order for isort to correctly differentiate between first- and third-party
    imports, we need to pass in a configuration object that tells isort where
    to look for first-party imports.
    """
    return isort.Config(
        src_paths=(path, *src_paths),  # Resolve first-party imports
        py_version="all",  # Ignore stdlib imports from all stdlib versions
    )


ISORT_FALLBACK_CONFIG = make_isort_config(Path("."))


def parse_code(
    code: str, *, source: Location, local_context: isort.Config = ISORT_FALLBACK_CONFIG
) -> Iterator[ParsedImport]:
    """Extract import statements from a string containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the code.
    """

    def is_external_import(name: str) -> bool:
        return isort.place_module(name, config=local_context) == "THIRDPARTY"

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


def parse_notebook_file(
    path: Path, local_context: Optional[isort.Config] = None
) -> Iterator[ParsedImport]:
    """Extract import statements from an ipynb notebook.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the file.
    """
    if not local_context:
        local_context = make_isort_config(Path("."), (path.parent,))

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
                    yield from parse_code(
                        "".join(lines), source=source, local_context=local_context
                    )
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


def parse_python_file(
    path: Path, local_context: Optional[isort.Config] = None
) -> Iterator[ParsedImport]:
    """Extract import statements from a file containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the file.
    """
    if not local_context:
        local_context = make_isort_config(Path("."), (path.parent,))
    yield from parse_code(
        path.read_text(), source=Location(path), local_context=local_context
    )


def parse_dir(path: Path) -> Iterator[ParsedImport]:
    """Extract import statements from Python files in the given directory.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in each file, but the order in which files are parsed is
    unspecified. Modules that are imported multiple times (in the same file or
    across several files) will be yielded multiple times.
    """
    for file in walk_dir(path):
        local_context = make_isort_config(
            path=path, src_paths=tuple(dirs_between(path, file.parent))
        )
        if file.suffix == ".py":
            yield from parse_python_file(file, local_context=local_context)
        elif file.suffix == ".ipynb":
            yield from parse_notebook_file(file, local_context=local_context)


def parse_any_arg(arg: PathOrSpecial) -> Iterator[ParsedImport]:
    """Interpret the given command-line argument and invoke a suitable parser.

    These cases are handled:
      - arg == "-": Read code from stdin and pass to parse_code()
      - arg refers to a file: Call parse_python_file() or parse_notebook_file()
      - arg refers to a dir: Call parse_dir()

    Otherwise raise UnparseablePathException with a suitable error message.
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
        raise UnparseablePathException(
            ctx="Supported formats are .py and .ipynb; Cannot parse code",
            path=arg,
        )
    if arg.is_dir():
        logger.info("Parsing Python files under %s", arg)
        return parse_dir(arg)
    raise UnparseablePathException(
        ctx="Code path to parse is neither dir nor file", path=arg
    )
