"""Verify behavior of LocalPackageLookup looking at a given venv."""

import venv

from fawltydeps.packages import DependenciesMapping, LocalPackageLookup


def test_local_env__empty_venv__has_no_packages(tmp_path):
    venv.create(tmp_path, with_pip=False)
    lpl = LocalPackageLookup(tmp_path)
    assert lpl.packages == {}


def test_local_env__default_venv__contains_pip_and_setuptools(tmp_path):
    venv.create(tmp_path, with_pip=True)
    lpl = LocalPackageLookup(tmp_path)
    # We cannot do a direct comparison, as different Python/pip/setuptools
    # versions differ in exactly which packages are provided. The following
    # is a subset that we can expect across all of our supported versions.
    expect = {  # package name -> (subset of) provided import names
        "pip": {"pip"},
        "setuptools": {"setuptools", "pkg_resources"},
    }
    for package_name, import_names in expect.items():
        assert package_name in lpl.packages
        p = lpl.packages[package_name]
        assert package_name == p.package_name
        assert len(p.mappings) == 1
        assert DependenciesMapping.LOCAL_ENV in p.mappings
        assert import_names.issubset(p.mappings[DependenciesMapping.LOCAL_ENV])


def test_local_env__current_venv__contains_our_test_dependencies():
    lpl = LocalPackageLookup()
    expect_package_names = [
        # Present in all venvs:
        "pip",
        "setuptools",
        # FawltyDeps main deps
        "isort",
        "pydantic",
        # Test dependencies
        "hypothesis",
        "pytest",
    ]
    for package_name in expect_package_names:
        assert package_name in lpl.packages
