"""Test the mapping of dependency names to import names."""


import pytest

from fawltydeps.check import LocalPackageLookup, resolve_dependencies
from fawltydeps.types import DependenciesMapping, Package

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
            {"isort"},
            id="package_exposes_nothing__can_still_infer_import_name",
        ),
        pytest.param(
            "pip",
            {"pip"},
            id="package_exposes_one_entry__returns_entry",
        ),
        pytest.param(
            "setuptools",
            {"_distutils_hack", "pkg_resources", "setuptools"},
            id="package_exposes_many_entries__returns_all_entries",
        ),
        pytest.param(
            "SETUPTOOLS",
            {"_distutils_hack", "pkg_resources", "setuptools"},
            id="package_declared_in_capital_letters__is_successfully_mapped_with_d2i",
        ),
        pytest.param(
            "typing-extensions",
            {"typing_extensions"},
            id="package_with_hyphen__provides_import_name_with_underscore",
        ),
    ],
)
def test_LocalPackageLookup_lookup_package(dep_name, expect_import_names):
    lpl = LocalPackageLookup()
    actual = lpl.lookup_package(dep_name)
    if expect_import_names is None:
        assert actual is None
    else:
        assert actual.import_names == expect_import_names


@pytest.mark.parametrize(
    "dep_names,expected_packages",
    [
        pytest.param(
            ["pip"],
            {"pip": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}})},
            id="dependency_present_in_local_env__uses_d2i_mapping",
        ),
        pytest.param(
            ["pandas"],
            {"pandas": Package("pandas", {DependenciesMapping.IDENTITY: {"pandas"}})},
            id="dependency_not_present_in_local_env__uses_id_mapping",
        ),
        pytest.param(
            ["pandas", "pip"],
            {
                "pip": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
                "pandas": Package("pandas", {DependenciesMapping.IDENTITY: {"pandas"}}),
            },
            id="mixed_dependencies_in_local_env__uses_id_and_d2i_mapping",
        ),
        pytest.param(
            ["setuptools"],
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
            },
            id="dependency_present_in_local_env__uses_d2i_mapping_and_has_correct_imports",
        ),
    ],
)
def test_resolve_dependencies(dep_names, expected_packages):
    assert resolve_dependencies(dep_names) == expected_packages
