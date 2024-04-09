"""Parse Python source code and extract import statements."""

import ast
import json
import logging
import tokenize
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, Optional, Tuple, Union

import isort

from fawltydeps.types import (
    CodeSource,
    Location,
    ParsedImport,
    PathOrSpecial,
    UnparseablePathError,
)
from fawltydeps.utils import dirs_between

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


ISORT_FALLBACK_CONFIG = make_isort_config(Path())


def parse_code(
    code: Union[str, bytes],
    *,
    source: Location,
    local_context: isort.Config = ISORT_FALLBACK_CONFIG,
) -> Iterator[ParsedImport]:
    """Extract import statements from a (byte)string containing Python code.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the code.

    The given code can be either a str or a bytes object. If a bytes object is
    used, the approrpiate encoding of the source code will be auto-detected,
    but if a str object is used, we assume that the caller has already decoded
    the source correctly, e.g. by using the tokenize.open() helper or similar.
    For more details about Python source file encodings, please see
    https://docs.python.org/3/reference/lexical_analysis.html#encoding-declarations.
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


def parse_notebook_file(  # noqa: C901
    path: Path, local_context: Optional[isort.Config] = None
) -> Iterator[ParsedImport]:
    """Extract import statements from an ipynb notebook.

    Generate (i.e. yield) the module names that are imported in the order
    they appear in the file.
    """
    if not local_context:
        local_context = make_isort_config(Path(), (path.parent,))

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
        local_context = make_isort_config(Path(), (path.parent,))
    with tokenize.open(path) as pyfile:
        yield from parse_code(
            pyfile.read(), source=Location(path), local_context=local_context
        )


def parse_source(
    src: CodeSource, stdin: Optional[BinaryIO] = None
) -> Iterator[ParsedImport]:
    """Invoke a suitable parser for the given source.

    These cases are handled:
      - src.path == "<stdin>": Read code from stdin and call parse_code()
      - src.path is a *.py file: Call parse_python_file()
      - src.path is a *.ipynb file: Call parse_notebook_file()
    """
    if src.path == "<stdin>":
        if stdin is None:
            raise UnparseablePathError(ctx="Missing <stdin> handle", path=Path("-"))
        logger.info("Parsing Python code from standard input")
        # 'isatty' checks if the stream is interactive.
        if stdin.isatty():
            logger.warning("Reading code from terminal input. Ctrl+D to stop.")
        return parse_code(stdin.read(), source=Location(src.path))

    assert isinstance(src.path, Path)  # noqa: S101, sanity check / silence mypy

    local_context = (
        None
        if src.base_dir is None
        else make_isort_config(
            path=src.base_dir,
            src_paths=tuple(dirs_between(src.base_dir, src.path.parent)),
        )
    )

    if src.path.suffix == ".py":
        logger.info("Parsing Python file %s", src.path)
        return parse_python_file(src.path, local_context)
    if src.path.suffix == ".ipynb":
        logger.info("Parsing Notebook file %s", src.path)
        return parse_notebook_file(src.path, local_context)
    raise RuntimeError("MISMATCH BETWEEN CODE PATH AND CODE PARSERS!")


def parse_sources(
    sources: Iterable[CodeSource], stdin: Optional[BinaryIO] = None
) -> Iterator[ParsedImport]:
    """Parse import statements from the given sources."""
    for source in sources:
        yield from parse_source(source, stdin)


def validate_code_source(
    path: PathOrSpecial, base_dir: Optional[Path] = None
) -> Optional[CodeSource]:
    """Check if the given file path is a valid source for parsing imports.

    - Return the given path as a CodeSource object iff it is a .py or .ipynb
      file (or the "<stdin>" special case).
    - Return None if this is a directory that must be traversed further to find
      parseable files within.
    - Raise UnparseablePathError if the given path cannot be parsed.
    """
    if path == "<stdin>":
        return CodeSource(path, base_dir)
    assert isinstance(path, Path)  # noqa: S101, sanity check: SpecialPath handled above
    if path.is_dir():
        logger.info("Finding Python files under %s", path)
        return None
    return CodeSource(path, base_dir)
