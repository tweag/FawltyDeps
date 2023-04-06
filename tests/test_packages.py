"""Verify behavior of package lookup and mapping to import names."""

import logging
from typing import Dict, List, Optional

import pytest

from fawltydeps.packages import (
    DependenciesMapping,
    IdentityMapping,
    LocalPackageResolver,
    Package,
    UserDefinedMapping,
    resolve_dependencies,
)
from fawltydeps.types import UnparseablePathException

from .utils import SAMPLE_PROJECTS_DIR, test_vectors


def test_package__empty_package__matches_nothing():
    p = Package("foobar")  # no mappings
    assert p.package_name == "foobar"
    assert not p.is_used(["foobar"])


@pytest.mark.parametrize(
    "package_name,matching_imports,non_matching_imports",
    [
        pytest.param(
            "foobar",
            ["foobar", "and", "other", "names"],
            ["only", "other", "names", "foo_bar", "Foobar", "FooBar", "FOOBAR"],
            id="simple_lowercase_name__matches_itself_only",
        ),
        pytest.param(
            "FooBar",
            ["foobar", "and", "other", "names"],
            ["only", "other", "names", "foo_bar", "Foobar", "FooBar", "FOOBAR"],
            id="mixed_case_name__matches_lowercase_only",
        ),
        pytest.param(
            "typing-extensions",
            ["typing_extensions", "and", "other", "names"],
            ["typing-extensions", "typingextensions"],
            id="name_with_hyphen__matches_name_with_underscore_only",
        ),
        pytest.param(
            "Foo-Bar",
            ["foo_bar", "and", "other", "names"],
            ["foo-bar", "Foobar", "FooBar", "FOOBAR"],
            id="weird_name__matches_normalized_name_only",
        ),
    ],
)
def test_package__identity_mapping(
    package_name, matching_imports, non_matching_imports
):
    id_mapping = IdentityMapping()
    p = id_mapping.lookup_package(package_name)
    assert p.package_name == package_name  # package name is not normalized
    assert p.is_used(matching_imports)
    assert not p.is_used(non_matching_imports)


@pytest.mark.parametrize(
    "package_name,import_names,matching_imports,non_matching_imports",
    [
        pytest.param(
            "foobar",
            ["foobar"],
            ["foobar", "and", "other", "names"],
            ["only", "other", "names", "foo_bar", "Foobar", "FooBar", "FOOBAR"],
            id="simple_name_mapped_to_itself__matches_itself_only",
        ),
        pytest.param(
            "FooBar",
            ["FooBar"],
            ["FooBar", "and", "other", "names"],
            ["only", "other", "names", "foo_bar", "foobar", "FOOBAR"],
            id="mixed_case_name_mapped_to_itself__matches_exact_spelling_only",
        ),
        pytest.param(
            "typing-extensions",
            ["typing_extensions"],
            ["typing_extensions", "and", "other", "names"],
            ["typing-extensions", "typingextensions"],
            id="hyphen_name_mapped_to_underscore_name__matches_only_underscore_name",
        ),
        pytest.param(
            "Foo-Bar",
            ["blorp"],
            ["blorp", "and", "other", "names"],
            ["Foo-Bar", "foo-bar", "foobar", "FooBar", "FOOBAR", "Blorp", "BLORP"],
            id="weird_name_mapped_diff_name__matches_diff_name_only",
        ),
        pytest.param(
            "foobar",
            ["foo", "bar", "baz"],
            ["foo", "and", "other", "names"],
            ["foobar", "and", "other", "names"],
            id="name_with_three_imports__matches_first_import",
        ),
        pytest.param(
            "foobar",
            ["foo", "bar", "baz"],
            ["bar", "and", "other", "names"],
            ["foobar", "and", "other", "names"],
            id="name_with_three_imports__matches_second_import",
        ),
        pytest.param(
            "foobar",
            ["foo", "bar", "baz"],
            ["baz", "and", "other", "names"],
            ["foobar", "and", "other", "names"],
            id="name_with_three_imports__matches_third_import",
        ),
    ],
)
def test_package__local_env_mapping(
    package_name, import_names, matching_imports, non_matching_imports
):
    p = Package(package_name)
    p.add_import_names(*import_names, mapping=DependenciesMapping.LOCAL_ENV)
    assert p.package_name == package_name  # package name is not normalized
    assert p.is_used(matching_imports)
    assert not p.is_used(non_matching_imports)


def test_package__both_mappings():
    id_mapping = IdentityMapping()
    p = id_mapping.lookup_package("FooBar")
    import_names = ["foo", "bar", "baz"]
    p.add_import_names(*import_names, mapping=DependenciesMapping.LOCAL_ENV)
    assert p.package_name == "FooBar"  # package name is not normalized
    assert p.is_used(["foobar"])  # but identity-mapped import name _is_.
    assert p.is_used(["foo"])
    assert p.is_used(["bar"])
    assert p.is_used(["baz"])
    assert not p.is_used(["fooba"])
    assert not p.is_used(["foobarbaz"])
    assert p.mappings == {
        DependenciesMapping.IDENTITY: {"foobar"},
        DependenciesMapping.LOCAL_ENV: {"foo", "bar", "baz"},
    }
    assert p.import_names == {"foobar", "foo", "bar", "baz"}


def test_user_defined_mapping__well_formated_input_file__parses_correctly(
    write_tmp_files,
):
    tmp_path = write_tmp_files(
        {
            "mapping.toml": """\
                apache-airflow = ["airflow"]
                attrs = ["attr", "attrs"]
            """
        }
    )
    udm = UserDefinedMapping(tmp_path / "mapping.toml")
    mapped_packages = udm.packages
    assert set(mapped_packages.keys()) == {"apache_airflow", "attrs"}


def test_user_defined_mapping__input_is_no_file__raises_unparsable_path_exeption():
    with pytest.raises(UnparseablePathException):
        UserDefinedMapping(SAMPLE_PROJECTS_DIR)


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
def test_LocalPackageResolver_lookup_packages(dep_name, expect_import_names):
    lpl = LocalPackageResolver()
    actual = lpl.lookup_packages({dep_name})
    if expect_import_names is None:
        assert actual == {}
    else:
        assert len(actual) == 1
        assert actual[dep_name].import_names == expect_import_names


# The deps in each category should be disjoint
non_locally_installed_deps = ["pandas", "numpy", "other"]
locally_installed_deps = {
    "setuptools": [
        "_distutils_hack",
        "pkg_resources",
        "setuptools",
    ],
    "pip": ["pip"],
    "isort": ["isort"],
}
user_defined_deps = {"apache-airflow": ["airflow"]}

user_defined_mapping = "\n".join(
    [f'{dep} = ["{",".join(imports)}"]' for dep, imports in user_defined_deps.items()]
)


def generate_expected_resolved_deps(
    locally_installed_deps: Optional[Dict[str, List[str]]] = None,
    non_locally_installed_deps: Optional[List[str]] = None,
    user_defined_deps: Optional[Dict[str, List[str]]] = None,
):
    ret = {}
    if locally_installed_deps:
        ret.update(
            {
                dep: Package(
                    dep,
                    {DependenciesMapping.LOCAL_ENV: set(imports)},
                )
                for dep, imports in locally_installed_deps.items()
            }
        )
    if user_defined_deps:
        ret.update(
            {
                dep: Package(
                    dep,
                    {DependenciesMapping.USER_DEFINED: set(imports)},
                )
                for dep, imports in user_defined_deps.items()
            }
        )
    if non_locally_installed_deps:
        ret.update(
            {
                dep: Package(dep, {DependenciesMapping.IDENTITY: {dep}})
                for dep in non_locally_installed_deps
            }
        )
    return ret


@pytest.mark.parametrize(
    "dep_names,user_mapping,expected",
    [
        pytest.param([], None, {}, id="no_deps__empty_dict"),
        pytest.param(
            non_locally_installed_deps,
            None,
            generate_expected_resolved_deps(
                non_locally_installed_deps=non_locally_installed_deps
            ),
            id="uninstalled_deps__use_identity_mapping",
        ),
        pytest.param(
            locally_installed_deps,
            None,
            generate_expected_resolved_deps(
                locally_installed_deps=locally_installed_deps
            ),
            id="installed_deps__use_local_env_mapping",
        ),
        pytest.param(
            list(locally_installed_deps.keys()) + non_locally_installed_deps,
            None,
            generate_expected_resolved_deps(
                locally_installed_deps=locally_installed_deps,
                non_locally_installed_deps=non_locally_installed_deps,
            ),
            id="mixed_deps__uses_mixture_of_identity_and_local_env_mapping",
        ),
        pytest.param(
            non_locally_installed_deps
            + list(locally_installed_deps.keys())
            + list(user_defined_deps.keys()),
            user_defined_mapping,
            generate_expected_resolved_deps(
                locally_installed_deps=locally_installed_deps,
                non_locally_installed_deps=non_locally_installed_deps,
                user_defined_deps=user_defined_deps,
            ),
            id="mixed_deps__uses_mixture_of_user_defined_identity_and_local_env_mapping",
        ),
        pytest.param(
            non_locally_installed_deps + list(locally_installed_deps.keys()),
            user_defined_mapping,
            generate_expected_resolved_deps(
                locally_installed_deps=locally_installed_deps,
                non_locally_installed_deps=non_locally_installed_deps,
            ),
            id="mixed_deps__unaffected_by_nonmatching_user_defined_mapping",
        ),
    ],
)
def test_resolve_dependencies__focus_on_mappings(
    dep_names, user_mapping, expected, write_tmp_files
):
    user_mapping_path = None
    if user_mapping is not None:
        tmp_path = write_tmp_files({"mapping.toml": user_mapping})
        user_mapping_path = tmp_path / "mapping.toml"

    assert (
        resolve_dependencies(
            dep_names,
            custom_mapping_path=user_mapping_path,
        )
        == expected
    )


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_resolve_dependencies(vector):
    dep_names = [dd.name for dd in vector.declared_deps]
    assert resolve_dependencies(dep_names) == vector.expect_resolved_deps


def test_resolve_dependencies__informs_once_when_id_mapping_is_used(caplog):
    dep_names = ["some-foo", "pip", "some-foo"]
    expect = {
        "pip": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
        "some-foo": Package("some-foo", {DependenciesMapping.IDENTITY: {"some_foo"}}),
    }
    expect_log = [
        (
            "fawltydeps.packages",
            logging.INFO,
            "'some-foo' was not resolved. Assuming it can be imported as 'some_foo'.",
        )
    ]
    caplog.set_level(logging.INFO)
    assert resolve_dependencies(dep_names) == expect
    assert caplog.record_tuples == expect_log
