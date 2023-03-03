"""Test the imports to dependencies comparison function."""
from pathlib import Path
from typing import Dict, List

import pytest

from fawltydeps.check import LocalPackageLookup, compare_imports_to_dependencies
from fawltydeps.settings import Settings
from fawltydeps.types import (
    DeclaredDependency,
    DependenciesMapping,
    Location,
    Package,
    ParsedImport,
    UndeclaredDependency,
    UnusedDependency,
)

from .utils import deps_factory

local_env = LocalPackageLookup()


def imports_factory(*imports: str) -> List[ParsedImport]:
    return [ParsedImport(imp, Location("<stdin>")) for imp in imports]


def resolved_factory(*deps: str) -> Dict[str, Package]:
    def mapping_for_dep(dep: str) -> DependenciesMapping:
        if local_env.lookup_package(dep) is None:
            return DependenciesMapping.IDENTITY
        return DependenciesMapping.LOCAL_ENV

    return {dep: Package(dep, {mapping_for_dep(dep): {dep}}) for dep in deps}


def undeclared_factory(*deps: str) -> List[UndeclaredDependency]:
    return [UndeclaredDependency(dep, [Location("<stdin>")]) for dep in deps]


def unused_factory(*deps: str) -> List[UnusedDependency]:
    return [UnusedDependency(dep, [Location(Path("foo"))]) for dep in deps]


@pytest.mark.parametrize(
    "imports,dependencies,ignore_unused,ignore_undeclared,expected",
    [
        pytest.param([], [], [], [], ({}, [], []), id="no_import_no_dependencies"),
        pytest.param(
            imports_factory("pandas"),
            [],
            [],
            [],
            ({}, undeclared_factory("pandas"), []),
            id="one_import_no_dependencies",
        ),
        pytest.param(
            [],
            deps_factory("pandas"),
            [],
            [],
            (resolved_factory("pandas"), [], unused_factory("pandas")),
            id="no_imports_one_dependency",
        ),
        pytest.param(
            imports_factory("pandas"),
            deps_factory("pandas"),
            [],
            [],
            (resolved_factory("pandas"), [], []),
            id="matched_import_with_dependency",
        ),
        pytest.param(
            imports_factory("pandas", "numpy"),
            deps_factory("pandas", "scipy"),
            [],
            [],
            (
                resolved_factory("pandas", "scipy"),
                undeclared_factory("numpy"),
                unused_factory("scipy"),
            ),
            id="mixed_imports_with_unused_and_undeclared_dependencies",
        ),
        pytest.param(
            imports_factory("pandas")
            + [ParsedImport("numpy", Location(Path("my_file.py"), lineno=3))],
            deps_factory("pandas", "scipy"),
            [],
            [],
            (
                resolved_factory("pandas", "scipy"),
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
            deps_factory("pip"),
            ["pip"],
            [],
            (resolved_factory("pip"), [], []),
            id="one_ignored_and_unused_dep__not_reported_as_unused",
        ),
        pytest.param(
            imports_factory("isort"),
            deps_factory("isort"),
            ["isort"],
            [],
            (resolved_factory("isort"), [], []),
            id="one_ignored_and_used_dep__not_reported_as_unused",
        ),
        pytest.param(
            imports_factory("isort"),
            deps_factory(),
            ["isort"],
            [],
            ({}, undeclared_factory("isort"), []),
            id="one_ignored_and_undeclared_dep__reported_as_undeclared",
        ),
        pytest.param(
            imports_factory("pandas", "numpy"),
            deps_factory("pandas", "isort", "flake8"),
            ["isort"],
            [],
            (
                resolved_factory("pandas", "isort", "flake8"),
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
            ({}, [], []),
            id="one_ignored_undeclared_dep__not_reported_as_undeclared",
        ),
        pytest.param(
            imports_factory("isort"),
            deps_factory("isort"),
            [],
            ["isort"],
            (resolved_factory("isort"), [], []),
            id="one_ignored_and_declared_dep__not_reported_as_undeclared",
        ),
        pytest.param(
            [],
            deps_factory("isort"),
            [],
            ["isort"],
            (resolved_factory("isort"), [], unused_factory("isort")),
            id="one_ignored_import_declared_as_dep__reported_as_unused",
        ),
        pytest.param(
            imports_factory("pandas", "numpy", "not_valid"),
            deps_factory("pandas", "flake8"),
            [],
            ["not_valid"],
            (
                resolved_factory("pandas", "flake8"),
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
                resolved_factory("pandas", "flake8", "isort"),
                undeclared_factory("numpy"),
                unused_factory("flake8"),
            ),
            id="mixed_dependencies__report_only_non_ignored_unused_and_non_ignored_undeclared",
        ),
        pytest.param(
            [],
            [
                DeclaredDependency(
                    name="Pip", source=Location(Path("requirements1.txt"))
                ),
                DeclaredDependency(
                    name="pip", source=Location(Path("requirements2.txt"))
                ),
            ],
            [],
            [],
            (
                {
                    "Pip": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
                    "pip": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
                },
                [],
                [
                    UnusedDependency("Pip", [Location(Path("requirements1.txt"))]),
                    UnusedDependency("pip", [Location(Path("requirements2.txt"))]),
                ],
            ),
            id="deps_with_diff_name_for_the_same_import",
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
