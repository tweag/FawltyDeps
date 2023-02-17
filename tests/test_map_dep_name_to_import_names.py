"""Test the mapping of dependency names to import names."""


from pathlib import Path

import pytest

from fawltydeps.check import LocalPackageLookup, dependencies_to_imports_mapping
from fawltydeps.types import DeclaredDependency, DependenciesMapping, Location

from .utils import deps_factory

# TODO: These tests are not fully isolated, i.e. they do not control the
# virtualenv in which they run. For now, we assume that we are running in an
# environment where at least these packages are available:
# - setuptools (exposes multiple import names, including pkg_resources)
# - pip (exposes a single import name: pip)
# - isort (exposes no top_level.txt, but 'isort' import name can be inferred)


@pytest.mark.parametrize(
    "dep_name,expect_import_names",
    [
        pytest.param(
            "NOT_A_PACKAGE",
            None,
            id="missing_package__returns_None",
        ),
        pytest.param(
            "isort",
            ("isort",),
            id="package_exposes_nothing__can_still_infer_import_name",
        ),
        pytest.param(
            "pip",
            ("pip",),
            id="package_exposes_one_entry__returns_entry",
        ),
        pytest.param(
            "setuptools",
            ("_distutils_hack", "pkg_resources", "setuptools"),
            id="package_exposes_many_entries__returns_all_entries",
        ),
    ],
)
def test_LocalPackageLookup_lookup_package(dep_name, expect_import_names):
    lpl = LocalPackageLookup()
    assert lpl.lookup_package(dep_name) == expect_import_names


@pytest.mark.parametrize(
    "dep_names,expected_declared_dependencies",
    [
        pytest.param(
            ["pip"],
            [
                DeclaredDependency(
                    name="pip",
                    source=Location(Path("foo")),
                    import_names=("pip",),
                    mapping=DependenciesMapping.DEPENDENCY_TO_IMPORT,
                )
            ],
            id="dependency_present_in_local_env__uses_d2i_mapping",
        ),
        pytest.param(
            ["pandas"],
            deps_factory("pandas"),
            id="dependency_not_present_in_local_env__uses_id_mapping",
        ),
        pytest.param(
            ["pandas", "pip"],
            deps_factory("pandas")
            + [
                DeclaredDependency(
                    name="pip",
                    source=Location(Path("foo")),
                    import_names=("pip",),
                    mapping=DependenciesMapping.DEPENDENCY_TO_IMPORT,
                )
            ],
            id="mixed_dependencies_in_local_env__uses_id_and_d2i_mapping",
        ),
        pytest.param(
            ["setuptools"],
            [
                DeclaredDependency(
                    name="setuptools",
                    source=Location(Path("foo")),
                    import_names=(
                        "_distutils_hack",
                        "pkg_resources",
                        "setuptools",
                    ),
                    mapping=DependenciesMapping.DEPENDENCY_TO_IMPORT,
                )
            ],
            id="dependency_present_in_local_env__uses_d2i_mapping_and_has_correct_imports",
        ),
    ],
)
def test_dependencies_to_imports_mapping(dep_names, expected_declared_dependencies):
    collected_dependencies = deps_factory(*dep_names)
    mapped_dependencies = dependencies_to_imports_mapping(collected_dependencies)

    assert mapped_dependencies == expected_declared_dependencies
