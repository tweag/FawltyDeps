"""Test the imports to dependencies comparison function."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import pytest

from fawltydeps.check import (
    LocalPackageLookup,
    calculate_undeclared,
    calculate_unused,
    compare_imports_to_dependencies,
    resolve_dependencies,
)
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

# TODO: These tests are not fully isolated, i.e. they do not control the
# virtualenv in which they run. For now, we assume that we are running in an
# environment where at least these packages are available:
# - setuptools (exposes multiple import names, including pkg_resources)
# - pip (exposes a single import name: pip)
# - isort (exposes no top_level.txt, but 'isort' import name can be inferred)

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


@dataclass
class FDTestVector:  # pylint: disable=too-many-instance-attributes
    """Test vectors for various parts of the FawltyDeps core logic."""

    id: str
    imports: List[ParsedImport] = field(default_factory=list)
    declared_deps: List[DeclaredDependency] = field(default_factory=list)
    ignore_unused: List[str] = field(default_factory=list)
    ignore_undeclared: List[str] = field(default_factory=list)
    expect_resolved_deps: Dict[str, Package] = field(default_factory=dict)
    expect_undeclared_deps: List[UndeclaredDependency] = field(default_factory=list)
    expect_unused_deps: List[UnusedDependency] = field(default_factory=list)


testdata = [
    FDTestVector("no_imports_no_deps"),
    FDTestVector(
        "one_import_no_deps",
        imports=imports_factory("pandas"),
        expect_undeclared_deps=undeclared_factory("pandas"),
    ),
    FDTestVector(
        "no_imports_one_dep",
        declared_deps=deps_factory("pandas"),
        expect_resolved_deps=resolved_factory("pandas"),
        expect_unused_deps=unused_factory("pandas"),
    ),
    FDTestVector(
        "matched_import_with_dep",
        imports=imports_factory("pandas"),
        declared_deps=deps_factory("pandas"),
        expect_resolved_deps=resolved_factory("pandas"),
    ),
    FDTestVector(
        "mixed_imports_with_unused_and_undeclared_deps",
        imports=imports_factory("pandas", "numpy"),
        declared_deps=deps_factory("pandas", "scipy"),
        expect_resolved_deps=resolved_factory("pandas", "scipy"),
        expect_undeclared_deps=undeclared_factory("numpy"),
        expect_unused_deps=unused_factory("scipy"),
    ),
    FDTestVector(
        "mixed_imports_from_diff_files_with_unused_and_undeclared_deps",
        imports=imports_factory("pandas")
        + [ParsedImport("numpy", Location(Path("my_file.py"), lineno=3))],
        declared_deps=deps_factory("pandas", "scipy"),
        expect_resolved_deps=resolved_factory("pandas", "scipy"),
        expect_undeclared_deps=[
            UndeclaredDependency(
                "numpy",
                [Location(Path("my_file.py"), lineno=3)],
            )
        ],
        expect_unused_deps=unused_factory("scipy"),
    ),
    FDTestVector(
        "unused_dep_that_is_ignore_unused__not_reported_as_unused",
        declared_deps=deps_factory("pip"),
        ignore_unused=["pip"],
        expect_resolved_deps=resolved_factory("pip"),
    ),
    FDTestVector(
        "used_dep_that_is_ignore_unused__not_reported_as_unused",
        imports=imports_factory("isort"),
        declared_deps=deps_factory("isort"),
        ignore_unused=["isort"],
        expect_resolved_deps=resolved_factory("isort"),
    ),
    FDTestVector(
        "undeclared_dep_that_is_ignore_unused__reported_as_undeclared",
        imports=imports_factory("isort"),
        ignore_unused=["isort"],
        expect_undeclared_deps=undeclared_factory("isort"),
    ),
    FDTestVector(
        "mixed_deps__report_undeclared_and_non_ignored_unused",
        imports=imports_factory("pandas", "numpy"),
        declared_deps=deps_factory("pandas", "isort", "flake8"),
        ignore_unused=["isort"],
        expect_resolved_deps=resolved_factory("pandas", "isort", "flake8"),
        expect_undeclared_deps=undeclared_factory("numpy"),
        expect_unused_deps=unused_factory("flake8"),
    ),
    FDTestVector(
        "undeclared_dep_that_is_ignore_undeclared__not_reported_as_undeclared",
        imports=imports_factory("invalid_import"),
        ignore_undeclared=["invalid_import"],
    ),
    FDTestVector(
        "declared_dep_that_is_ignore_undeclared__not_reported_as_undeclared",
        imports=imports_factory("isort"),
        declared_deps=deps_factory("isort"),
        ignore_undeclared=["isort"],
        expect_resolved_deps=resolved_factory("isort"),
    ),
    FDTestVector(
        "unused_dep_that_is_ignore_undeclared__reported_as_unused",
        declared_deps=deps_factory("isort"),
        ignore_undeclared=["isort"],
        expect_resolved_deps=resolved_factory("isort"),
        expect_unused_deps=unused_factory("isort"),
    ),
    FDTestVector(
        "mixed_deps__report_unused_and_non_ignored_undeclared",
        imports=imports_factory("pandas", "numpy", "not_valid"),
        declared_deps=deps_factory("pandas", "flake8"),
        ignore_undeclared=["not_valid"],
        expect_resolved_deps=resolved_factory("pandas", "flake8"),
        expect_undeclared_deps=undeclared_factory("numpy"),
        expect_unused_deps=unused_factory("flake8"),
    ),
    FDTestVector(
        "mixed_deps__report_only_non_ignored_unused_and_non_ignored_undeclared",
        imports=imports_factory("pandas", "numpy", "not_valid"),
        declared_deps=deps_factory("pandas", "flake8", "isort"),
        ignore_undeclared=["not_valid"],
        ignore_unused=["isort"],
        expect_resolved_deps=resolved_factory("pandas", "flake8", "isort"),
        expect_undeclared_deps=undeclared_factory("numpy"),
        expect_unused_deps=unused_factory("flake8"),
    ),
    FDTestVector(
        "deps_with_diff_name_for_the_same_import",
        declared_deps=[
            DeclaredDependency(name="Pip", source=Location(Path("requirements1.txt"))),
            DeclaredDependency(name="pip", source=Location(Path("requirements2.txt"))),
        ],
        expect_resolved_deps={
            "Pip": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
            "pip": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
        },
        expect_unused_deps=[
            UnusedDependency("Pip", [Location(Path("requirements1.txt"))]),
            UnusedDependency("pip", [Location(Path("requirements2.txt"))]),
        ],
    ),
]


@pytest.mark.parametrize(
    "dep_names,expected",
    [
        pytest.param([], {}, id="no_deps__empty_dict"),
        pytest.param(
            ["pandas", "numpy", "other"],
            {
                "pandas": Package("pandas", {DependenciesMapping.IDENTITY: {"pandas"}}),
                "numpy": Package("numpy", {DependenciesMapping.IDENTITY: {"numpy"}}),
                "other": Package("other", {DependenciesMapping.IDENTITY: {"other"}}),
            },
            id="uninstalled_deps__use_identity_mapping",
        ),
        pytest.param(
            ["pandas", "numpy", "other"],
            {
                "pandas": Package("pandas", {DependenciesMapping.IDENTITY: {"pandas"}}),
                "numpy": Package("numpy", {DependenciesMapping.IDENTITY: {"numpy"}}),
                "other": Package("other", {DependenciesMapping.IDENTITY: {"other"}}),
            },
            id="uninstalled_deps__use_identity_mapping",
        ),
        pytest.param(
            ["setuptools", "pip", "isort"],
            {
                "setuptools": Package(
                    "setuptools",
                    {
                        DependenciesMapping.LOCAL_ENV: {
                            "_distutils_hack",
                            "pkg_resources",
                            "setuptools",
                        }
                    },
                ),
                "pip": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
                "isort": Package("isort", {DependenciesMapping.LOCAL_ENV: {"isort"}}),
            },
            id="installed_deps__use_local_env_mapping",
        ),
    ],
)
def test_resolve_dependencies__focus_on_mappings(dep_names, expected):
    assert resolve_dependencies(dep_names) == expected


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in testdata])
def test_resolve_dependencies(vector):
    dep_names = [dd.name for dd in vector.declared_deps]
    assert resolve_dependencies(dep_names) == vector.expect_resolved_deps


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in testdata])
def test_calculate_undeclared(vector):
    settings = Settings(ignore_undeclared=vector.ignore_undeclared)
    actual = calculate_undeclared(vector.imports, vector.expect_resolved_deps, settings)
    assert actual == vector.expect_undeclared_deps


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in testdata])
def test_calculate_unused(vector):
    settings = Settings(ignore_unused=vector.ignore_unused)
    actual = calculate_unused(
        vector.imports, vector.declared_deps, vector.expect_resolved_deps, settings
    )
    assert actual == vector.expect_unused_deps


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in testdata])
def test_compare_imports_to_dependencies(vector):
    settings = Settings(
        ignore_unused=vector.ignore_unused, ignore_undeclared=vector.ignore_undeclared
    )
    actual = compare_imports_to_dependencies(
        vector.imports, vector.declared_deps, settings
    )
    actual_resolved_deps, actual_undeclared_deps, actual_unused_deps = actual
    assert actual_resolved_deps == vector.expect_resolved_deps
    assert actual_undeclared_deps == vector.expect_undeclared_deps
    assert actual_unused_deps == vector.expect_unused_deps
