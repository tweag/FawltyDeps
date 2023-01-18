"""Test the imports to dependencies comparison function."""
from pathlib import Path
from typing import List

import pytest

from fawltydeps.check import (
    DependencyComparison,
    FileLocation,
    compare_imports_to_dependencies,
)
from fawltydeps.extract_dependencies import DeclaredDependency
from fawltydeps.extract_imports import ParsedImport


def dependencies_factory(data: List[str]) -> List[DeclaredDependency]:
    return [DeclaredDependency(name=d, location=Path("")) for d in data]


def imports_factory(data: List[str]) -> List[ParsedImport]:
    return [ParsedImport(name=d, location=None, lineno=None) for d in data]


@pytest.mark.parametrize(
    "imports,dependencies,expected",
    [
        pytest.param(
            [], [], DependencyComparison({}, set()), id="no_import_no_dependencies"
        ),
        pytest.param(
            imports_factory(["sys"]),
            [],
            DependencyComparison({}, set()),
            id="stdlib_import_no_dependencies",
        ),
        pytest.param(
            imports_factory(["pandas"]),
            [],
            DependencyComparison({"pandas": []}, set()),
            id="non_stdlib_import_no_dependencies",
        ),
        pytest.param(
            [],
            dependencies_factory(["pandas"]),
            DependencyComparison({}, set(["pandas"])),
            id="no_imports_one_dependency",
        ),
        pytest.param(
            imports_factory(["sys", "pandas"]),
            dependencies_factory(["pandas"]),
            DependencyComparison({}, set()),
            id="mixed_imports_non_stdlib_dependency",
        ),
        pytest.param(
            imports_factory(["sys", "pandas"]),
            [],
            DependencyComparison({"pandas": []}, set()),
            id="mixed_imports_no_dependencies",
        ),
        pytest.param(
            imports_factory(["sys"]),
            dependencies_factory(["pandas"]),
            DependencyComparison({}, set(["pandas"])),
            id="stdlib_import_and_non_stdlib_dependency",
        ),
        pytest.param(
            imports_factory(["sys", "pandas", "numpy"]),
            dependencies_factory(["pandas", "scipy"]),
            DependencyComparison({"numpy": []}, set(["scipy"])),
            id="mixed_imports_with_unused_and_undeclared_dependencies",
        ),
        pytest.param(
            imports_factory(["sys", "pandas"])
            + [ParsedImport(name="numpy", location=Path("my_file.py"), lineno=3)],
            dependencies_factory(["pandas", "scipy"]),
            DependencyComparison(
                {"numpy": [FileLocation(Path("my_file.py"), 3)]},
                set(["scipy"]),
            ),
            id="mixed_imports_with_unused_and_undeclared_dependencies",
        ),
    ],
)
def test_compare_imports_to_dependencies(imports, dependencies, expected):
    """Ensures the comparison method returns the expected unused and undeclared dependencies"""
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected
