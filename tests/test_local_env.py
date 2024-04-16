"""Verify behavior of package module looking at a given Python environment."""

import sys
import venv
from pathlib import Path
from typing import Iterator

import pytest

from fawltydeps.packages import (
    IdentityMapping,
    LocalPackageResolver,
    Package,
    SysPathPackageResolver,
    pyenv_sources,
    resolve_dependencies,
    setup_resolvers,
)
from fawltydeps.utils import site_packages

major, minor = sys.version_info[:2]

# When the user gives us a --pyenv arg that points to a (non-PEP582) Python
# environment, what are the the possible paths inside that Python environment
# that they might point at (and that we should accept)?
env_subdirs = [
    "",
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

# When the user gives us a --pyenv arg that points to a Python virtualenv
# on Windows, what are the the possible paths inside that Python environment
# that they might point at (and that we should accept)?
windows_subdirs = [
    "",
    "Lib",
    str(site_packages()),
]


@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="Only relevant to Windows virtual environment",
)
@pytest.mark.parametrize(
    "subdir", [pytest.param(d, id=f"venv:{d}") for d in windows_subdirs]
)
def test_find_package_dirs__various_paths_in_venv_windows(tmp_path, subdir):
    venv.create(tmp_path, with_pip=False)
    path = tmp_path / subdir
    expect = {site_packages(tmp_path)}
    assert set(LocalPackageResolver.find_package_dirs(path)) == expect


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="Not relevant to Windows virtual environment",
)
@pytest.mark.parametrize(
    "subdir", [pytest.param(d, id=f"venv:{d}") for d in env_subdirs]
)
def test_find_package_dirs__various_paths_in_venv(tmp_path, subdir):
    venv.create(tmp_path, with_pip=False)
    path = tmp_path / subdir
    expect = {tmp_path / f"lib/python{major}.{minor}/site-packages"}
    assert set(LocalPackageResolver.find_package_dirs(path)) == expect


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Not relevant to Windows virtual environment"
)
@pytest.mark.parametrize(
    "subdir", [pytest.param(d, id=f"poetry2nix:{d}") for d in env_subdirs]
)
def test_find_package_dirs__various_paths_in_poetry2nix_env(write_tmp_files, subdir):
    # A directory structure that resembles a minimal poetry2nix environment:
    tmp_path = write_tmp_files(
        {
            "bin/python": "",
            f"lib/python{major}.{minor}/site-packages/some_package.py": "",
        }
    )
    path = tmp_path / subdir
    expect = {tmp_path / f"lib/python{major}.{minor}/site-packages"}
    assert set(LocalPackageResolver.find_package_dirs(path)) == expect


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Not relevant to Windows virtual environment"
)
@pytest.mark.parametrize(
    "subdir", [pytest.param(d, id=f"pep582:{d}") for d in pep582_subdirs]
)
def test_find_package_dirs__various_paths_in_pypackages(write_tmp_files, subdir):
    # A directory structure that resembles a minimal PEP582 __pypackages__ dir:
    tmp_path = write_tmp_files(
        {
            f"__pypackages__/{major}.{minor}/lib/some_package.py": "",
        }
    )
    path = tmp_path / subdir
    expect = {tmp_path / f"__pypackages__/{major}.{minor}/lib"}
    assert set(LocalPackageResolver.find_package_dirs(path)) == expect


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Not relevant to Windows virtual environment"
)
@pytest.mark.parametrize(
    "subdir",
    [pytest.param(d, id=f"pep582:{d}") for d in pep582_subdirs]
    + [pytest.param(".venv/" + d, id=f"venv:.venv/{d}") for d in env_subdirs],
)
def test_find_package_dirs__envs_with_multiple_package_dirs(write_tmp_files, subdir):
    # A directory structure that contains multiple Python environments, and
    # multiple package dirs inside each Python environments:
    tmp_path = write_tmp_files(
        {
            f"__pypackages__/{major}.{minor}/lib/first_package.py": "",
            f"__pypackages__/{major}.{minor + 1}/lib/second_package.py": "",
            ".venv/bin/python": "",
            f".venv/lib/python{major}.{minor}/site-packages/third_package.py": "",
            f".venv/lib/python{major}.{minor + 1}/site-packages/fourth_package.py": "",
        }
    )
    path = tmp_path / subdir
    actual = set(LocalPackageResolver.find_package_dirs(path))

    def expected_package_dirs(base: Path, subdir: str) -> Iterator[Path]:
        is_version_agnostic = f"{major}.{minor}" not in subdir
        if subdir.startswith("__pypackages__"):
            yield base / f"__pypackages__/{major}.{minor}/lib"
            if is_version_agnostic:  # expect _all_ versioned dirs
                yield base / f"__pypackages__/{major}.{minor + 1}/lib"
        else:
            assert subdir.startswith(".venv/")
            yield base / f".venv/lib/python{major}.{minor}/site-packages"
            if is_version_agnostic:  # expect _all_ versioned dirs
                yield base / f".venv/lib/python{major}.{minor + 1}/site-packages"

    assert actual == set(expected_package_dirs(tmp_path, subdir))


def test_local_env__empty_venv__has_no_packages(tmp_path):
    venv.create(tmp_path, with_pip=False)
    lpl = LocalPackageResolver(pyenv_sources(tmp_path))
    assert lpl.packages == {}


def test_local_env__default_venv__contains_pip(tmp_path):
    # Different Python versions install different packages in their default venv
    # (e.g. Python v3.12 no longer installs setuptools). Also, package versions
    # will differ in exactly which import names are provided. The only common
    # subset that can expect across all of our supported versions is that the
    # "pip" package is installed, and that it provides a "pip" import name.
    venv.create(tmp_path, with_pip=True)
    lpl = LocalPackageResolver(pyenv_sources(tmp_path))
    expect_location = site_packages(tmp_path)
    assert "pip" in lpl.packages
    pip = lpl.packages["pip"]
    assert pip.package_name == "pip"
    assert "pip" in pip.import_names
    assert str(expect_location) in pip.debug_info


def test_sys_path_env__contains_prepared_packages(isolate_default_resolver):
    isolate_default_resolver(
        {
            "pip": {"pip"},
            "setuptools": {"setuptools", "pkg_resources"},
            "isort": {"isort"},
            "pydantic": {"pydantic"},
            "pytest": {"pytest"},
        }
    )
    sys_path = SysPathPackageResolver()
    expect_package_names = ["pip", "setuptools", "isort", "pydantic", "pytest"]
    for package_name in expect_package_names:
        assert package_name in sys_path.packages


def test_sys_path_env__prefers_first_package_found(isolate_default_resolver):
    # Add the same package twice, The one that ends up _first_ in sys.path is
    # the one that Python would end up importing, and it is therefore also the
    # one that we should resolve to.

    site_dir1 = isolate_default_resolver({"other": {"skipped"}})
    site_dir2 = isolate_default_resolver({"other": {"actual"}})
    assert site_dir1 != site_dir2
    assert sys.path[0] == str(site_dir2)
    actual = SysPathPackageResolver().lookup_packages({"other"})
    assert actual == {
        "other": Package(
            "other", {"actual"}, SysPathPackageResolver, {str(site_dir2): {"actual"}}
        ),
    }


def test_local_env__multiple_pyenvs__can_find_packages_in_all(fake_venv):
    venv_dir1, site_dir1 = fake_venv({"some_module": {"some_module"}})
    venv_dir2, site_dir2 = fake_venv({"other-module": {"other_module"}})
    lpl = LocalPackageResolver(pyenv_sources(venv_dir1, venv_dir2))
    assert lpl.lookup_packages({"some_module", "other-module"}) == {
        "some_module": Package(
            "some_module",
            {"some_module"},
            LocalPackageResolver,
            {str(site_dir1): {"some_module"}},
        ),
        "other-module": Package(
            "other_module",
            {"other_module"},
            LocalPackageResolver,
            {str(site_dir2): {"other_module"}},
        ),
    }


def test_local_env__multiple_pyenvs__merges_imports_for_same_package(fake_venv):
    venv_dir1, site_dir1 = fake_venv({"some_module": {"first_import"}})
    venv_dir2, site_dir2 = fake_venv({"some_module": {"second_import"}})
    lpl = LocalPackageResolver(pyenv_sources(venv_dir1, venv_dir2))
    assert lpl.lookup_packages({"some_module"}) == {
        "some_module": Package(
            "some_module",
            {"first_import", "second_import"},
            LocalPackageResolver,
            {
                str(site_dir1): {"first_import"},
                str(site_dir2): {"second_import"},
            },
        ),
    }


def test_resolve_dependencies__in_empty_venv__reverts_to_id_mapping(tmp_path):
    venv.create(tmp_path, with_pip=False)
    id_mapping = IdentityMapping()
    actual = resolve_dependencies(
        ["pip", "setuptools"], setup_resolvers(pyenv_srcs=pyenv_sources(tmp_path))
    )
    assert actual == id_mapping.lookup_packages({"pip", "setuptools"})


def test_resolve_dependencies__in_fake_venv__returns_local_and_id_deps(fake_venv):
    venv_dir, site_packages = fake_venv(
        {
            "pip": {"pip"},
            "setuptools": {"setuptools", "pkg_resources"},
            "empty_pkg": set(),
        }
    )
    actual = resolve_dependencies(
        ["PIP", "pandas", "empty-pkg"],
        setup_resolvers(pyenv_srcs=pyenv_sources(venv_dir)),
    )
    assert actual == {
        "PIP": Package(
            "pip", {"pip"}, LocalPackageResolver, {str(site_packages): {"pip"}}
        ),
        "pandas": Package("pandas", {"pandas"}, IdentityMapping),
        "empty-pkg": Package(
            "empty_pkg", set(), LocalPackageResolver, {str(site_packages): set()}
        ),
    }


def test_resolve_dependencies__in_2_fake_venvs__returns_local_and_id_deps(fake_venv):
    venv_dir1, site_dir1 = fake_venv({"some_module": {"first_import"}})
    venv_dir2, site_dir2 = fake_venv(
        {"some_module": {"second_import"}, "other-module": {"other_module"}}
    )
    actual = resolve_dependencies(
        ["some_module", "pandas", "other_module"],
        setup_resolvers(pyenv_srcs=pyenv_sources(venv_dir1, venv_dir2)),
    )
    assert actual == {
        "some_module": Package(
            "some_module",
            {"first_import", "second_import"},
            LocalPackageResolver,
            {
                str(site_dir1): {"first_import"},
                str(site_dir2): {"second_import"},
            },
        ),
        "pandas": Package("pandas", {"pandas"}, IdentityMapping),
        "other_module": Package(
            "other_module",
            {"other_module"},
            LocalPackageResolver,
            {str(site_dir2): {"other_module"}},
        ),
    }


def test_resolve_dependencies__when_no_env_found__fallback_to_current():
    # When no Python env is found by traverse_project, we end up with zero
    # PyEnvSource objects in Analysis.sources, and Analysis.resolved_deps uses
    # enables the use_current_env flag to setup_resolvers() in this case.
    resolvers = list(setup_resolvers(use_current_env=True))

    # The resulting resolvers should include a single SysPathPackageResolver.
    syspath_resolvers = [r for r in resolvers if isinstance(r, SysPathPackageResolver)]
    assert len(syspath_resolvers) == 1
    spr = syspath_resolvers[0]

    # The only thing we can assume about the _current_ env (in which FD runs)
    # is that "fawltydeps" is installed (hence resolved via our 'spr'), and that
    # "other_module" is not installed (and thus resolved with IdentityMapping).
    actual = resolve_dependencies(["fawltydeps", "other_module"], resolvers)
    assert actual == {
        "fawltydeps": spr.lookup_packages({"fawltydeps"})["fawltydeps"],
        "other_module": Package("other_module", {"other_module"}, IdentityMapping),
    }
