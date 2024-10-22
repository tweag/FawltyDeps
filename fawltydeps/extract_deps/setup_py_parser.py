"""Code for best-effort parsing of setup.py files."""

import ast
import logging
import sys
import tokenize
from pathlib import Path
from typing import Iterable, Iterator, Union

from fawltydeps.limited_eval import CannotResolve, VariableTracker
from fawltydeps.types import DeclaredDependency, Location

from .requirements_parser import parse_one_req

logger = logging.getLogger(__name__)


class DependencyParsingError(Exception):
    """Error raised when parsing of dependency fails."""

    def __init__(self, node: ast.AST):
        super().__init__(node)
        self.node = node


def parse_setup_py(path: Path) -> Iterator[DeclaredDependency]:  # noqa: C901
    """Extract dependencies (package names) from setup.py.

    This file can contain arbitrary Python code, and simply executing it has
    potential security implications. For now, we parse it with the `ast` module,
    looking for the first call to a `setup()` function, and attempt to extract
    the `install_requires` and `extras_require` keyword args from that function
    call.
    """
    source = Location(path)
    # Attempt to keep track of simple variable assignments (name -> value)
    # declared in the setup.py prior to the setup() call, so that we can
    # resolve any variable references in the arguments to the setup() call.
    tracked_vars = VariableTracker(source)

    def _extract_deps_from_value(
        value: Union[str, Iterable[str]],
        node: ast.AST,
    ) -> Iterator[DeclaredDependency]:
        if isinstance(value, str):  # expected list, but got string
            value = [value]  # parse as if a single-element list is given
        try:
            for item in value:
                yield parse_one_req(item, source)
        except ValueError as e:  # parse_one_req() failed
            raise DependencyParsingError(node) from e

    def _extract_deps_from_setup_call(
        node: ast.Call,
    ) -> Iterator[DeclaredDependency]:
        for keyword in node.keywords:
            try:
                if keyword.arg == "install_requires":
                    value = tracked_vars.resolve(keyword.value)
                    yield from _extract_deps_from_value(value, keyword.value)
                elif keyword.arg == "extras_require":
                    value = tracked_vars.resolve(keyword.value)
                    if not isinstance(value, dict):
                        raise DependencyParsingError(keyword.value)
                    for items in value.values():
                        yield from _extract_deps_from_value(items, keyword.value)
            except (DependencyParsingError, CannotResolve) as exc:
                if sys.version_info >= (3, 9):
                    unparsed_content = ast.unparse(exc.node)
                else:
                    unparsed_content = ast.dump(exc.node)
                logger.warning(
                    f"Could not parse contents of `{keyword.arg}`: {unparsed_content} in {source}."
                )

    def _is_setup_function_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "setup"
        )

    try:
        with tokenize.open(path) as setup_py:
            setup_contents = ast.parse(setup_py.read(), filename=str(source.path))
    except SyntaxError as e:
        logger.error(f"Could not parse {path}: {e}")
        return
    for node in ast.walk(setup_contents):
        tracked_vars.evaluate(node)
        if _is_setup_function_call(node):
            # Below line is not checked by mypy, but `_is_setup_function_call`
            # makes sure that `node` is of a proper type.
            yield from _extract_deps_from_setup_call(node.value)  # type: ignore[attr-defined]
            break
