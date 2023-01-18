"""Test the imports to dependencies comparison function."""
import pytest

from fawltydeps.check import DependencyComparison, compare_imports_to_dependencies


@pytest.mark.parametrize(
    "imports,dependencies,expected",
    [
        pytest.param(
            [], [], DependencyComparison(set(), set()), id="no_import_no_dependencies"
        ),
        pytest.param(
            ["pandas"],
            [],
            DependencyComparison(set(["pandas"]), set()),
            id="one_import_no_dependencies",
        ),
        pytest.param(
            [],
            ["pandas"],
            DependencyComparison(set(), set(["pandas"])),
            id="no_imports_one_dependency",
        ),
        pytest.param(
            ["pandas"],
            ["pandas"],
            DependencyComparison(set(), set()),
            id="matched_import_with_dependency",
        ),
        pytest.param(
            ["pandas", "numpy"],
            ["pandas", "scipy"],
            DependencyComparison(set(["numpy"]), set(["scipy"])),
            id="mixed_imports_with_unused_and_undeclared_dependencies",
        ),
    ],
)
def test_compare_imports_to_dependencies(imports, dependencies, expected):
    """Ensures the comparison method returns the expected unused and undeclared dependencies"""
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected
