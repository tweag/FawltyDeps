"""Verify behavior of package lookup and mapping to import names."""

import logging
from textwrap import dedent

import pytest

from fawltydeps.packages import (
    IdentityMapping,
    LocalPackageResolver,
    Package,
    SysPathPackageResolver,
    UserDefinedMapping,
    resolve_dependencies,
    setup_resolvers,
    suggest_packages,
)
from fawltydeps.types import (
    PyEnvSource,
    UnparseablePathError,
    UnresolvedDependenciesError,
)

from .utils import (
    SAMPLE_PROJECTS_DIR,
    default_sys_path_env_for_tests,
    ignore_package_debug_info,
    test_vectors,
)


def test_package__empty_package__matches_nothing():
    p = Package("foobar", set(), IdentityMapping)  # no import names
    assert p.package_name == "foobar"
    assert not p.is_used(["foobar"])


@pytest.mark.parametrize(
    ("package_name", "matching_imports", "non_matching_imports"),
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
        pytest.param(
            "foo-stubs",
            ["foo", "foo-stubs"],
            ["foo_stubs"],
            id="type-stubs__preserve_-stubs_suffix_in_normalization",
        ),
    ],
)
def test_package__identity_mapping(
    package_name, matching_imports, non_matching_imports
):
    id_mapping = IdentityMapping()
    p = id_mapping.lookup_package(package_name)
    assert p.package_name == package_name
    assert p.normalized_name == Package.normalize_name(package_name)
    assert p.is_used(matching_imports)
    assert not p.is_used(non_matching_imports)


@pytest.mark.parametrize(
    ("package_name", "import_names", "matching_imports", "non_matching_imports"),
    [
        pytest.param(
            "foobar",
            {"foobar"},
            ["foobar", "and", "other", "names"],
            ["only", "other", "names", "foo_bar", "Foobar", "FooBar", "FOOBAR"],
            id="simple_name_mapped_to_itself__matches_itself_only",
        ),
        pytest.param(
            "FooBar",
            {"FooBar"},
            ["FooBar", "and", "other", "names"],
            ["only", "other", "names", "foo_bar", "foobar", "FOOBAR"],
            id="mixed_case_name_mapped_to_itself__matches_exact_spelling_only",
        ),
        pytest.param(
            "typing-extensions",
            {"typing_extensions"},
            ["typing_extensions", "and", "other", "names"],
            ["typing-extensions", "typingextensions"],
            id="hyphen_name_mapped_to_underscore_name__matches_only_underscore_name",
        ),
        pytest.param(
            "Foo-Bar",
            {"blorp"},
            ["blorp", "and", "other", "names"],
            ["Foo-Bar", "foo-bar", "foobar", "FooBar", "FOOBAR", "Blorp", "BLORP"],
            id="weird_name_mapped_diff_name__matches_diff_name_only",
        ),
        pytest.param(
            "foobar",
            {"foo", "bar", "baz"},
            ["foo", "and", "other", "names"],
            ["foobar", "and", "other", "names"],
            id="name_with_three_imports__matches_first_import",
        ),
        pytest.param(
            "foobar",
            {"foo", "bar", "baz"},
            ["bar", "and", "other", "names"],
            ["foobar", "and", "other", "names"],
            id="name_with_three_imports__matches_second_import",
        ),
        pytest.param(
            "foobar",
            {"foo", "bar", "baz"},
            ["baz", "and", "other", "names"],
            ["foobar", "and", "other", "names"],
            id="name_with_three_imports__matches_third_import",
        ),
        pytest.param(
            "types-requests",
            {"requests-stubs"},
            ["requests-stubs", "and", "other", "names"],
            ["requests_stubs", "and", "other", "names"],
            id="name_with_stubs_suffix__matches_name_with_stubs_suffix",
        ),
        pytest.param(
            "types-requests",
            {"requests-stubs"},
            ["requests", "and", "other", "names"],
            ["types_requests", "and", "other", "names"],
            id="name_with_stubs_suffix__matches_name_without_suffix",
        ),
    ],
)
def test_package__local_env_mapping(
    package_name, import_names, matching_imports, non_matching_imports, fake_venv
):
    _venv_dir, site_dir = fake_venv({package_name: import_names})
    lpl = LocalPackageResolver({PyEnvSource(site_dir)})
    normalized_name = Package.normalize_name(package_name)
    p = lpl.packages[normalized_name]
    assert p.package_name == package_name
    assert p.normalized_name == normalized_name
    assert p.resolved_with is LocalPackageResolver
    assert p.is_used(matching_imports)
    assert not p.is_used(non_matching_imports)


@pytest.mark.parametrize(
    ("mapping_files_content", "custom_mapping", "expect"),
    [
        pytest.param(
            [
                """\
                apache-airflow = ["airflow"]
                attrs = ["attr", "attrs"]
                """
            ],
            None,
            {
                "apache_airflow": Package(
                    "apache-airflow", {"airflow"}, UserDefinedMapping
                ),
                "attrs": Package("attrs", {"attr", "attrs"}, UserDefinedMapping),
            },
            id="well_formated_input_file__parses_correctly",
        ),
        pytest.param(
            [
                """\
                apache-airflow = ["airflow"]
                attrs = ["attr", "attrs"]
                """,
                """\
                apache-airflow = ["baz"]
                foo = ["bar"]
                """,
            ],
            None,
            {
                "apache_airflow": Package(
                    "apache-airflow", {"airflow", "baz"}, UserDefinedMapping
                ),
                "attrs": Package("attrs", {"attr", "attrs"}, UserDefinedMapping),
                "foo": Package("foo", {"bar"}, UserDefinedMapping),
            },
            id="well_formated_input_2files__parses_correctly",
        ),
        pytest.param(
            [
                """\
                apache-airflow = ["airflow"]
                attrs = ["attr", "attrs"]
                """,
                """\
                apache-airflow = ["baz"]
                foo = ["bar"]
                """,
            ],
            {"apache-airflow": ["unicorn"]},
            {
                "apache_airflow": Package(
                    "apache-airflow", {"airflow", "baz", "unicorn"}, UserDefinedMapping
                ),
                "attrs": Package("attrs", {"attr", "attrs"}, UserDefinedMapping),
                "foo": Package("foo", {"bar"}, UserDefinedMapping),
            },
            id="well_formated_input_2files_and_config__parses_correctly",
        ),
        pytest.param(
            [
                """\
                types_requests = ["requests-stubs"]
                """
            ],
            None,
            {
                "types_requests": Package(
                    "types_requests", {"requests-stubs"}, UserDefinedMapping
                ),
            },
            id="stubs_only_package",
        ),
    ],
)
def test_user_defined_mapping__well_formated_input_file__parses_correctly(
    mapping_files_content,
    custom_mapping,
    expect,
    tmp_path,
):
    custom_mapping_files = set()
    for i, mapping in enumerate(mapping_files_content):
        custom_mapping_file = tmp_path / f"mapping{i}.toml"
        custom_mapping_file.write_text(dedent(mapping))
        custom_mapping_files.add(custom_mapping_file)

    udm = UserDefinedMapping(
        mapping_paths=custom_mapping_files, custom_mapping=custom_mapping
    )
    actual = ignore_package_debug_info(udm.packages)
    assert actual == expect


def test_user_defined_mapping__input_is_no_file__raises_unparsable_path_exeption():
    with pytest.raises(UnparseablePathError):
        UserDefinedMapping({SAMPLE_PROJECTS_DIR})


def test_user_defined_mapping__no_input__returns_empty_mapping():
    udm = UserDefinedMapping()
    assert len(udm.packages) == 0


@pytest.mark.parametrize(
    ("dep_name", "expect_import_names"),
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
        pytest.param(
            "types-setuptools",
            {"pkg_resources-stubs", "setuptools-stubs"},
            id="package_using_typeshed__provides_import_name_with_stubs_suffix",
        ),
    ],
)
def test_SysPathPackageResolver_lookup_packages(
    isolate_default_resolver, dep_name, expect_import_names
):
    isolate_default_resolver(default_sys_path_env_for_tests)
    sys_path = SysPathPackageResolver()
    actual = sys_path.lookup_packages({dep_name})
    if expect_import_names is None:
        assert actual == {}
    else:
        assert len(actual) == 1
        assert actual[dep_name].import_names == expect_import_names


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_resolve_dependencies(vector, isolate_default_resolver):
    dep_names = [dd.name for dd in vector.declared_deps]
    isolate_default_resolver(default_sys_path_env_for_tests)
    actual = ignore_package_debug_info(
        resolve_dependencies(dep_names, setup_resolvers(use_current_env=True))
    )
    assert actual == vector.expect_resolved_deps


def test_resolve_dependencies__informs_once_when_id_mapping_is_used(
    caplog, isolate_default_resolver
):
    dep_names = ["some-foo", "pip", "some-foo"]
    isolate_default_resolver(default_sys_path_env_for_tests)
    expect = {
        "pip": Package("pip", {"pip"}, SysPathPackageResolver),
        "some-foo": Package("some-foo", {"some_foo"}, IdentityMapping),
    }
    expect_log = [
        (
            "fawltydeps.packages",
            logging.INFO,
            "'some-foo' was not resolved. Assuming it can be imported as 'some_foo'.",
        )
    ]
    caplog.set_level(logging.INFO)
    actual = ignore_package_debug_info(
        resolve_dependencies(dep_names, setup_resolvers(use_current_env=True))
    )
    assert actual == expect
    assert caplog.record_tuples == expect_log


def test_resolve_dependencies__unresolved_dependencies__UnresolvedDependenciesError_raised():
    dep_names = ["foo", "bar"]

    with pytest.raises(UnresolvedDependenciesError):
        resolve_dependencies(dep_names, setup_resolvers(install_deps=True))


@pytest.mark.parametrize(
    ("import_name", "expect_package_names"),
    [
        pytest.param(
            "something_else",
            set(),
            id="import_not_in_env__yields_no_suggestions",
        ),
        pytest.param(
            "foo",
            {"foo_package"},
            id="import_with_one_match_in_venv__yields_one_suggestion",
        ),
        pytest.param(
            "bar",
            {"bar_package"},
            id="other_import_with_one_match_in_venv__yields_one_suggestion",
        ),
        pytest.param(
            "baz",
            {"bar_package", "baz_package"},
            id="import_with_two_matches_in_venv__yields_two_suggestions",
        ),
        pytest.param(
            "other_module",
            {"SomeOther-Package"},
            id="import_with_one_match_in_venv__yields_orig_package_name",
        ),
    ],
)
def test_suggest_packages_in_fake_venv(import_name, expect_package_names, fake_venv):
    _venv_dir, site_dir = fake_venv(
        {
            "foo_package": {"foo"},
            "bar_package": {"bar", "baz"},
            "baz_package": {"baz"},
            "SomeOther-Package": {"other_module"},
        }
    )
    lpl = LocalPackageResolver({PyEnvSource(site_dir)})
    actual = {p.package_name for p in suggest_packages(import_name, [lpl])}
    assert actual == expect_package_names


@pytest.mark.parametrize(
    ("import_name", "expect_package_names"),
    [
        pytest.param(
            "something_else",
            set(),
            id="import_not_in_env__yields_no_suggestions",
        ),
        pytest.param(
            "isort",
            {"isort"},
            id="import_with_same_name_match_in_venv__yields_package",
        ),
        pytest.param(
            "pkg_resources",
            {"setuptools"},
            id="import_with_diff_name_match_in_venv__yields_package",
        ),
        pytest.param(
            "requests-stubs",
            {"types-requests"},
            id="import_with_diff_name_match_in_venv__yields_orig_package_name",
        ),
    ],
)
def test_suggest_packages_in_default_sys_path_env_for_tests(
    import_name, expect_package_names, isolate_default_resolver
):
    isolate_default_resolver(default_sys_path_env_for_tests)
    resolvers = list(setup_resolvers(use_current_env=True))
    actual = {p.package_name for p in suggest_packages(import_name, resolvers)}
    assert actual == expect_package_names
