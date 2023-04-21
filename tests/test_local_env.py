"""Verify behavior of package module looking at a given Python environment."""
import sys
import venv

import pytest

from fawltydeps.packages import (
    DependenciesMapping,
    IdentityMapping,
    LocalPackageResolver,
    Package,
    resolve_dependencies,
)

from .project_helpers import TarballPackage

major, minor = sys.version_info[:2]

# When the user gives us a --pyenv arg that points to a (non-PEP582) Python
# environment, what are the the possible paths inside that Python environment
# that they might point at (and that we should accept)?
env_subdirs = [
    "",
    "bin",
    "lib",
    f"lib/python{major}.{minor}",
    f"lib/python{major}.{minor}/site-packages",
]

# When the user gives us a --pyenv arg that points to a PEP582 __pypackages__
# dir, what are the the possible paths inside that __pypackages__ dir that they
# might point at (and that we should accept)?
pep582_subdirs = [
    "__pypackages__",
    f"__pypackages__/{major}.{minor}",
    f"__pypackages__/{major}.{minor}/lib",
]


@pytest.mark.parametrize(
    "subdir", [pytest.param(d, id=f"venv:{d}") for d in env_subdirs]
)
def test_determine_package_dir__various_paths_in_venv(tmp_path, subdir):
    venv.create(tmp_path, with_pip=False)
    path = tmp_path / subdir
    expect = tmp_path / f"lib/python{major}.{minor}/site-packages"
    assert LocalPackageResolver.determine_package_dir(path) == expect


@pytest.mark.parametrize(
    "subdir", [pytest.param(d, id=f"poetry2nix:{d}") for d in env_subdirs]
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
    assert LocalPackageResolver.determine_package_dir(path) == expect


@pytest.mark.parametrize(
    "subdir", [pytest.param(d, id=f"pep582:{d}") for d in pep582_subdirs]
)
def test_determine_package_dir__various_paths_in_pypackages(write_tmp_files, subdir):
    # A directory structure that resembles a minimal PEP582 __pypackages__ dir:
    tmp_path = write_tmp_files(
        {
            f"__pypackages__/{major}.{minor}/lib/some_package.py": "",
        }
    )
    path = tmp_path / subdir
    expect = tmp_path / f"__pypackages__/{major}.{minor}/lib"
    assert LocalPackageResolver.determine_package_dir(path) == expect


def test_local_env__empty_venv__has_no_packages(tmp_path):
    venv.create(tmp_path, with_pip=False)
    lpl = LocalPackageResolver(tmp_path)
    assert lpl.packages == {}


def test_local_env__default_venv__contains_pip_and_setuptools(tmp_path):
    venv.create(tmp_path, with_pip=True)
    lpl = LocalPackageResolver(tmp_path)
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


def test_local_env__current_venv__contains_prepared_packages(isolate_default_resolver):
    isolate_default_resolver(
        {
            "pip": {"pip"},
            "setuptools": {"setuptools", "pkg_resources"},
            "isort": {"isort"},
            "pydantic": {"pydantic"},
            "pytest": {"pytest"},
        }
    )
    lpl = LocalPackageResolver()
    expect_package_names = ["pip", "setuptools", "isort", "pydantic", "pytest"]
    for package_name in expect_package_names:
        assert package_name in lpl.packages


def test_resolve_dependencies__in_empty_venv__reverts_to_id_mapping(tmp_path):
    venv.create(tmp_path, with_pip=False)
    id_mapping = IdentityMapping()
    actual = resolve_dependencies(["pip", "setuptools"], pyenv_path=tmp_path)
    assert actual == id_mapping.lookup_packages({"pip", "setuptools"})


def test_resolve_dependencies__in_fake_venv__returns_local_and_id_deps(fake_venv):
    venv_dir, _ = fake_venv(
        {
            "pip": {"pip"},
            "setuptools": {"setuptools", "pkg_resources"},
            "empty_pkg": set(),
        }
    )
    actual = resolve_dependencies(["PIP", "pandas", "empty-pkg"], pyenv_path=venv_dir)
    assert actual == {
        "PIP": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
        "pandas": Package("pandas", {DependenciesMapping.IDENTITY: {"pandas"}}),
        "empty-pkg": Package("empty_pkg", {DependenciesMapping.LOCAL_ENV: set()}),
    }


def test_on_installed_venv__returns_local_deps(request, monkeypatch):
    cache_dir = TarballPackage.cache_dir(request.config.cache)
    TarballPackage.get_tarballs(request.config.cache)
    # set the test's env variables so that pip would install from the local repo
    monkeypatch.setenv("PIP_NO_INDEX", "True")
    monkeypatch.setenv("PIP_FIND_LINKS", str(cache_dir))

    actual = resolve_dependencies(
        ["leftpadx", "click"], pyenv_path=None, install_deps=True
    )
    assert actual == {
        "leftpadx": Package("leftpadx", {DependenciesMapping.LOCAL_ENV: {"leftpad"}}),
        "click": Package("click", {DependenciesMapping.LOCAL_ENV: {"click"}}),
    }
