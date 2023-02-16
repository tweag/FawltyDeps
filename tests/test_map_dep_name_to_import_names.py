"""Test the mapping of dependency names to import names."""


import pytest

from fawltydeps.check import LocalPackageLookup

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
def test_find_import_names_from_package_name(dep_name, expect_import_names):
    lpl = LocalPackageLookup()
    assert lpl.lookup_package(dep_name) == expect_import_names
