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
    pyenv_sources,
    resolve_dependencies,
    setup_resolvers,
)

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


@pytest.mark.parametrize(
    "subdir", [pytest.param(d, id=f"venv:{d}") for d in env_subdirs]
)
def test_find_package_dirs__various_paths_in_venv(tmp_path, subdir):
    venv.create(tmp_path, with_pip=False)
    path = tmp_path / subdir
    expect = {tmp_path / f"lib/python{major}.{minor}/site-packages"}
    assert set(LocalPackageResolver.find_package_dirs(path)) == expect


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


def test_local_env__default_venv__contains_pip_and_setuptools(tmp_path):
    venv.create(tmp_path, with_pip=True)
    lpl = LocalPackageResolver(pyenv_sources(tmp_path))
    # We cannot do a direct comparison, as different Python/pip/setuptools
    # versions differ in exactly which packages are provided. The following
    # is a subset that we can expect across all of our supported versions.
    expect = {  # package name -> (subset of) provided import names
        "pip": {"pip"},
        "setuptools": {"setuptools", "pkg_resources"},
    }
    expect_location = tmp_path / f"lib/python{major}.{minor}/site-packages"
    for expect_package_name, expect_import_names in expect.items():
        assert expect_package_name in lpl.packages
        p = lpl.packages[expect_package_name]
        assert expect_package_name == p.package_name
        for expect_import_name in expect_import_names:
            assert expect_import_name in p.import_names
            assert str(expect_location) in p.debug_info


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


def test_local_env__prefers_first_package_found_in_sys_path(isolate_default_resolver):
    # Add the same package twice, The one that ends up _first_ in sys.path is
    # the one that Python would end up importing, and it is therefore also the
    # one that we should resolve to.

    site_dir1 = isolate_default_resolver({"other": {"skipped"}})
    site_dir2 = isolate_default_resolver({"other": {"actual"}})
    assert site_dir1 != site_dir2
    assert sys.path[0] == str(site_dir2)
    actual = LocalPackageResolver().lookup_packages({"other"})
    assert actual == {
        "other": Package(
            "other", {"actual"}, LocalPackageResolver, {str(site_dir2): {"actual"}}
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
