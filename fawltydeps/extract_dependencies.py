"Collect declared dependencies of the project"

import ast
import logging
import os
from pathlib import Path
from typing import Iterator, Tuple

from pkg_resources import parse_requirements

logger = logging.getLogger(__name__)


def parse_requirements_contents(
    text: str, path_hint: Path
) -> Iterator[Tuple[str, Path]]:
    """
    Extract dependencies (packages names) from the requirement.txt file
    and other following Requirements File Format. For more information, see
    https://pip.pypa.io/en/stable/reference/requirements-file-format/.
    """
    for requirement in parse_requirements(text):
        yield (requirement.key, path_hint)


def parse_setup_contents(text: str, path_hint: Path) -> Iterator[Tuple[str, Path]]:
    """
    Extract dependencies (package names) from setup.py.
    Function call `setup` where dependencies are listed
    is at the outermost level of setup.py file.
    """
    setup_contents = ast.parse(text, filename=str(path_hint))

    def _handle_dependencies(deps: ast.List) -> Iterator[Tuple[str, Path]]:
        for element in deps.elts:
            if isinstance(element, ast.Constant):
                yield from parse_requirements_contents(
                    element.value, path_hint=path_hint
                )

    def _extract_deps_from_setup_call(node: ast.Call) -> Iterator[Tuple[str, Path]]:
        for keyword in node.keywords:
            if keyword.arg == "install_requires":
                if isinstance(keyword.value, ast.List):
                    yield from _handle_dependencies(keyword.value)
                else:
                    logger.warning(
                        "Could not parse contents of `install_requires`: %s",
                        ast.unparse(keyword.value),
                    )

            if keyword.arg == "extras_require":
                if isinstance(keyword.value, ast.Dict):
                    logger.debug(ast.dump(keyword.value))
                    for elements in keyword.value.values:
                        logger.debug(ast.dump(elements))
                        if isinstance(elements, ast.List):
                            yield from _handle_dependencies(elements)
                        else:
                            logger.warning(
                                "Could not parse contents of `extras_require` for elements: %s",
                                ast.unparse(elements),
                            )
                else:
                    logger.warning(
                        "Could not parse contents of `extras_require`: %s",
                        ast.unparse(keyword.value),
                    )

    def _is_setup_function_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "setup"
        )

    for node in ast.walk(setup_contents):
        if _is_setup_function_call(node):
            yield from _extract_deps_from_setup_call(node.value)
            break


def extract_dependencies(path: Path) -> Iterator[Tuple[str, Path]]:
    """
    Extract dependencies from supported file types.
    Traverse directory tree to find matching files.
    Call handlers for each file type to extract dependencies.
    """
    parsers = {
        "requirements.txt": parse_requirements_contents,
        "requirements.in": parse_requirements_contents,
        "setup.py": parse_setup_contents,
    }
    # TODO extract dependencies from pyproject.toml

    for root, _dirs, files in os.walk(path):
        for filename in files:
            if filename in parsers:
                parser = parsers[filename]
                current_path = Path(root, filename)
                logger.debug(f"Extracting dependency from {current_path}.")
                yield from parser(current_path.read_text(), path_hint=current_path)
