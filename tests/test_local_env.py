"""Verify behavior of package module looking at a given venv."""
import sys
import venv

import pytest

from fawltydeps.packages import (
    DependenciesMapping,
    LocalPackageLookup,
    Package,
    resolve_dependencies,
)

major, minor = sys.version_info[:2]

# When the user gives us a --venv arg, what are the the possible paths inside
# that Python environment that they might point at (that we should accept)
env_subdirs = [
    "",
    "bin",
    "lib",
    f"lib/python{major}.{minor}",
    f"lib/python{major}.{minor}/site-packages",
]


@pytest.mark.parametrize(
    "subdir", [pytest.param(d, id=f"venv:{d}") for d in env_subdirs]
)
def test_determine_package_dir__various_paths_in_venv(tmp_path, subdir):
    venv.create(tmp_path, with_pip=False)
    path = tmp_path / subdir
    expect = tmp_path / f"lib/python{major}.{minor}/site-packages"
    assert LocalPackageLookup.determine_package_dir(path) == expect


@pytest.mark.parametrize(
    "subdir", [pytest.param(d, id=f"venv:{d}") for d in env_subdirs]
)
def test_determine_package_dir__various_paths_in_poetry2nix_env(
    write_tmp_files, subdir
):
    # A directory structure that resembles a minimal poetry2nix environment:
    tmp_path = write_tmp_files(
        {
            "bin/python": "",
            f"lib/python{major}.{minor}/site-packages/some_package.py": "",
        }
    )
    path = tmp_path / subdir
    expect = tmp_path / f"lib/python{major}.{minor}/site-packages"
    assert LocalPackageLookup.determine_package_dir(path) == expect


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


def test_resolve_dependencies__in_empty_venv__reverts_to_id_mapping(tmp_path):
    venv.create(tmp_path, with_pip=False)
    actual = resolve_dependencies(["pip", "setuptools"], venv_path=tmp_path)
    assert actual == {
        "pip": Package.identity_mapping("pip"),
        "setuptools": Package.identity_mapping("setuptools"),
    }


def test_resolve_dependencies__in_fake_venv__returns_local_and_id_deps(fake_venv):
    venv_dir = fake_venv(
        {
            "pip": {"pip"},
            "setuptools": {"setuptools", "pkg_resources"},
            "empty_pkg": set(),
        }
    )
    actual = resolve_dependencies(["PIP", "pandas", "empty-pkg"], venv_path=venv_dir)
    assert actual == {
        "PIP": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
        "pandas": Package.identity_mapping("pandas"),
        "empty-pkg": Package("empty_pkg", {DependenciesMapping.LOCAL_ENV: set()}),
    }
