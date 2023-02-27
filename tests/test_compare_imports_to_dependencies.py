"""Test the imports to dependencies comparison function."""
from pathlib import Path
from typing import List

import pytest

from fawltydeps.check import compare_imports_to_dependencies
from fawltydeps.settings import Settings
from fawltydeps.types import (
    Location,
    ParsedImport,
    UndeclaredDependency,
    UnusedDependency,
)

from .utils import deps_factory


def imports_factory(*imports: str) -> List[ParsedImport]:
    return [ParsedImport(imp, Location("<stdin>")) for imp in imports]


def undeclared_factory(*deps: str) -> List[UndeclaredDependency]:
    return [UndeclaredDependency(dep, [Location("<stdin>")]) for dep in deps]


def unused_factory(*deps: str) -> List[UnusedDependency]:
    return [UnusedDependency(dep, [Location(Path("foo"))]) for dep in deps]


@pytest.mark.parametrize(
    "imports,dependencies,ignore_unused,ignore_undeclared,expected",
    [
        pytest.param([], [], [], [], ([], []), id="no_import_no_dependencies"),
        pytest.param(
            imports_factory("pandas"),
            [],
            [],
            [],
            (undeclared_factory("pandas"), []),
            id="one_import_no_dependencies",
        ),
        pytest.param(
            [],
            deps_factory("pandas"),
            [],
            [],
            ([], unused_factory("pandas")),
            id="no_imports_one_dependency",
        ),
        pytest.param(
            imports_factory("pandas"),
            deps_factory("pandas"),
            [],
            [],
            ([], []),
            id="matched_import_with_dependency",
        ),
        pytest.param(
            imports_factory("pandas", "numpy"),
            deps_factory("pandas", "scipy"),
            [],
            [],
            (undeclared_factory("numpy"), unused_factory("scipy")),
            id="mixed_imports_with_unused_and_undeclared_dependencies",
        ),
        pytest.param(
            imports_factory("pandas")
            + [ParsedImport("numpy", Location(Path("my_file.py"), lineno=3))],
            deps_factory("pandas", "scipy"),
            [],
            [],
            (
                [
                    UndeclaredDependency(
                        "numpy",
                        [Location(Path("my_file.py"), lineno=3)],
                    )
                ],
                unused_factory("scipy"),
            ),
            id="mixed_imports_from_diff_files_with_unused_and_undeclared_dependencies",
        ),
        pytest.param(
            [],
            deps_factory("black"),
            ["black"],
            [],
            ([], []),
            id="one_ignored_and_unused_dep__not_reported_as_unused",
        ),
        pytest.param(
            imports_factory("isort"),
            deps_factory("isort"),
            ["isort"],
            [],
            ([], []),
            id="one_ignored_and_used_dep__not_reported_as_unused",
        ),
        pytest.param(
            imports_factory("isort"),
            deps_factory(),
            ["isort"],
            [],
            (undeclared_factory("isort"), []),
            id="one_ignored_and_undeclared_dep__reported_as_undeclared",
        ),
        pytest.param(
            imports_factory("pandas", "numpy"),
            deps_factory("pandas", "isort", "flake8"),
            ["isort"],
            [],
            (
                undeclared_factory("numpy"),
                unused_factory("flake8"),
            ),
            id="mixed_dependencies__report_undeclared_and_non_ignored_unused",
        ),
        pytest.param(
            imports_factory("invalid_import"),
            [],
            [],
            ["invalid_import"],
            ([], []),
            id="one_ignored_undeclared_dep__not_reported_as_undeclared",
        ),
        pytest.param(
            imports_factory("isort"),
            deps_factory("isort"),
            [],
            ["isort"],
            ([], []),
            id="one_ignored_and_declared_dep__not_reported_as_undeclared",
        ),
        pytest.param(
            [],
            deps_factory("isort"),
            [],
            ["isort"],
            (
                [],
                unused_factory("isort"),
            ),
            id="one_ignored_import_declared_as_dep__reported_as_unused",
        ),
        pytest.param(
            imports_factory("pandas", "numpy", "not_valid"),
            deps_factory("pandas", "flake8"),
            [],
            ["not_valid"],
            (
                undeclared_factory("numpy"),
                unused_factory("flake8"),
            ),
            id="mixed_dependencies__report_unused_and_only_non_ignored_undeclared",
        ),
        pytest.param(
            imports_factory("pandas", "numpy", "not_valid"),
            deps_factory("pandas", "flake8", "isort"),
            ["isort"],
            ["not_valid"],
            (
                undeclared_factory("numpy"),
                unused_factory("flake8"),
            ),
            id="mixed_dependencies__report_only_non_ignored_unused_and_non_ignored_undeclared",
        ),
    ],
)
def test_compare_imports_to_dependencies(
    imports, dependencies, ignore_unused, ignore_undeclared, expected
):
    """Ensures the comparison method returns the expected unused and undeclared dependencies"""
    settings = Settings(
        ignore_unused=ignore_unused, ignore_undeclared=ignore_undeclared
    )
    obtained = compare_imports_to_dependencies(imports, dependencies, settings)
    assert obtained == expected
