"""Test the imports to dependencies comparison function."""
from pathlib import Path
from typing import List

import pytest

from fawltydeps.check import compare_imports_to_dependencies
from fawltydeps.types import (
    DeclaredDependency,
    DependencyComparison,
    Location,
    ParsedImport,
)


def dependencies_factory(data: List[str]) -> List[DeclaredDependency]:
    return [DeclaredDependency(name=d, source=Location(Path(""))) for d in data]


def imports_factory(data: List[str]) -> List[ParsedImport]:
    return [ParsedImport(name=d, source=Location("<stdin>")) for d in data]


@pytest.mark.parametrize(
    "imports,dependencies,expected",
    [
        pytest.param(
            [], [], DependencyComparison({}, set()), id="no_import_no_dependencies"
        ),
        pytest.param(
            imports_factory(["pandas"]),
            [],
            DependencyComparison({"pandas": [Location("<stdin>")]}, set()),
            id="one_import_no_dependencies",
        ),
        pytest.param(
            [],
            dependencies_factory(["pandas"]),
            DependencyComparison({}, set(["pandas"])),
            id="no_imports_one_dependency",
        ),
        pytest.param(
            imports_factory(["pandas"]),
            dependencies_factory(["pandas"]),
            DependencyComparison({}, set()),
            id="matched_import_with_dependency",
        ),
        pytest.param(
            imports_factory(["pandas", "numpy"]),
            dependencies_factory(["pandas", "scipy"]),
            DependencyComparison({"numpy": [Location("<stdin>")]}, set(["scipy"])),
            id="mixed_imports_with_unused_and_undeclared_dependencies",
        ),
        pytest.param(
            imports_factory(["pandas"])
            + [ParsedImport("numpy", Location(Path("my_file.py"), lineno=3))],
            dependencies_factory(["pandas", "scipy"]),
            DependencyComparison(
                {"numpy": [Location(Path("my_file.py"), lineno=3)]},
                set(["scipy"]),
            ),
            id="mixed_imports_from_diff_files_with_unused_and_undeclared_dependencies",
        ),
    ],
)
def test_compare_imports_to_dependencies(imports, dependencies, expected):
    """Ensures the comparison method returns the expected unused and undeclared dependencies"""
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected
