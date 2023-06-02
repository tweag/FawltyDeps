"""Fixtures for tests"""
import sys
import venv
from pathlib import Path
from tempfile import mkdtemp
from textwrap import dedent
from typing import Callable, Dict, Iterable, Optional, Set, Tuple, Union

import pytest

from fawltydeps.types import TomlData

from .project_helpers import TarballPackage


@pytest.fixture
def local_pypi(request, monkeypatch):
    cache_dir = TarballPackage.cache_dir(request.config.cache)
    TarballPackage.get_tarballs(request.config.cache)
    # set the test's env variables so that pip would install from the local repo
    monkeypatch.setenv("PIP_NO_INDEX", "True")
    monkeypatch.setenv("PIP_FIND_LINKS", str(cache_dir))


@pytest.fixture
def write_tmp_files(tmp_path: Path):
    def _inner(file_contents: Dict[str, str]) -> Path:
        for filename, contents in file_contents.items():
            path = tmp_path / filename
            assert path.relative_to(tmp_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(dedent(contents))
        return tmp_path

    return _inner


@pytest.fixture
def fake_venv(tmp_path):
    def create_one_fake_venv(
        fake_packages: Dict[str, Set[str]],
        *,
        venv_dir: Optional[Path] = None,
        py_version: Tuple[int, int] = sys.version_info[:2],
    ) -> Tuple[Path, Path]:
        if venv_dir is None:
            venv_dir = Path(mkdtemp(prefix="fake_venv.", dir=tmp_path))
        else:
            venv_dir.parent.mkdir(parents=True, exist_ok=True)
        venv.create(venv_dir, with_pip=False)

        # Create fake packages
        major, minor = py_version
        site_dir = venv_dir / f"lib/python{major}.{minor}/site-packages"
        assert site_dir.is_dir()
        for package_name, import_names in fake_packages.items():
            # Create just enough files under site_dir to fool importlib_metadata
            # into believing these are genuine packages
            dist_info_dir = site_dir / f"{package_name}-1.2.3.dist-info"
            dist_info_dir.mkdir()
            (dist_info_dir / "METADATA").write_text(
                f"Name: {package_name}\nVersion: 1.2.3\n"
            )
            top_level = dist_info_dir / "top_level.txt"
            top_level.write_text("".join(f"{name}\n" for name in sorted(import_names)))
            for name in import_names:
                (site_dir / f"{name}.py").touch()

        return venv_dir, site_dir

    return create_one_fake_venv


@pytest.fixture
def isolate_default_resolver(
    fake_venv: Callable[[Dict[str, Set[str]]], Tuple[Path, Path]], monkeypatch
):
    """Put a fake_venv at the start of sys.path to yield predictable Packages.

    Call the returned function to place a fake venv with the specified package
    mappings at the start of sys.path.

    Rationale:
    When testing resolve_dependencies() or anything that depends on
    LocalPackageResolver() with default/empty pyenv, it is important to realize
    that local packages will be resolved via sys.path. This is hard to fully
    isolate/mock in tests, but we can do the following to approximate isolation:
    - Use fake_venv() and pytest.monkeypatch.syspath_prepend(path) to make sure
      packages that we expect to find in the default environment are always
      found in this fake venv. This is achieved by using this fixture.
    - Populate this fake_venv with package that we expect to find in the default
      environment. These will then be resolved through the fake_venv to yield
      predictable import names and mapping descriptions.
    - Tests must make sure packages that they expect NOT to find in the default
      environment are chosen/spelled in ways to ensure they are indeed never
      found elsewhere in sys.path, as we are not able to isolate the resolver
      from sys.path.
    """

    def inner(fake_packages: Dict[str, Set[str]]) -> Path:
        _venv_dir, package_dir = fake_venv(fake_packages)
        monkeypatch.syspath_prepend(package_dir)
        return package_dir

    return inner


@pytest.fixture
def project_with_requirements(write_tmp_files):
    return write_tmp_files(
        {
            "requirements.txt": """\
                pandas
                click
                """,
            "subdir/requirements.txt": """\
                pandas
                tensorflow>=2
                """,
            # This file should be ignored:
            ".venv/requirements.txt": """\
                foo_package
                bar_package
                """,
            "python_file.py": "import django",
        }
    )


@pytest.fixture
def project_with_setup_and_requirements(write_tmp_files):
    return write_tmp_files(
        {
            "requirements.txt": """\
                pandas
                click
                """,
            "subdir/requirements.txt": """\
                pandas
                tensorflow>=2
                """,
            "setup.py": """\
                from setuptools import setup

                setup(
                    name="MyLib",
                    install_requires=["pandas", "click>=1.2"],
                    extras_require={
                        'annoy': ['annoy==1.15.2'],
                        'chinese': ['jieba']
                        }
                )
                """,
            "python_file.py": "import django",
        }
    )


@pytest.fixture
def project_with_setup_pyproject_and_requirements(write_tmp_files):
    return write_tmp_files(
        {
            "requirements.txt": """\
                pandas
                click
                """,
            "subdir/requirements.txt": """\
                pandas
                tensorflow>=2
                """,
            "setup.py": """\
                from setuptools import setup

                setup(
                    name="MyLib",
                    install_requires=["pandas", "click>=1.2"],
                    extras_require={
                        'annoy': ['annoy==1.15.2'],
                        'chinese': ['jieba']
                        }
                )
                """,
            "pyproject.toml": """\
                [project]
                name = "fawltydeps"

                dependencies = ["pandas", "pydantic>1.10.4"]

                [project.optional-dependencies]
                dev = ["pylint >= 2.15.8"]
            """,
            "python_file.py": "import django",
        }
    )


@pytest.fixture
def project_with_pyproject(write_tmp_files):
    return write_tmp_files(
        {
            "pyproject.toml": """\
                [project]
                name = "fawltydeps"

                dependencies = ["pandas", "pydantic>1.10.4"]

                [project.optional-dependencies]
                dev = ["pylint >= 2.15.8"]
            """,
            "python_file.py": "import django",
        }
    )


@pytest.fixture
def project_with_setup_cfg(write_tmp_files):
    return write_tmp_files(
        {
            "setup.cfg": """\
                [metadata]
                name = "fawltydeps"

                [options]
                install_requires =
                    pandas
                    django
                  
            """,
            "setup.py": """\
                import setuptools

                if __name__ == "__main__":
                    setuptools.setup()
            """,
            "python_file.py": "import django",
        }
    )


@pytest.fixture
def project_with_setup_with_cfg_pyproject_and_requirements(write_tmp_files):
    return write_tmp_files(
        {
            "requirements.txt": """\
                pandas
                click
            """,
            "subdir/dev-requirements.txt": """\
                black
            """,
            "subdir/requirements.txt": """\
                pandas
                tensorflow>=2
            """,
            "subdir/requirements-docs.txt": """\
                sphinx
            """,
            "setup.py": """\
                from setuptools import setup
                
                setup(use_scm_version=True)
            """,
            "setup.cfg": """\
                [metadata]
                name = "fawltydeps"

                [options]
                install_requires =
                    dependencyA
                    dependencyB
                  
            """,
            "pyproject.toml": """\
                [project]
                name = "fawltydeps"

                dependencies = ["pandas", "pydantic>1.10.4"]

                [project.optional-dependencies]
                dev = ["pylint >= 2.15.8"]
            """,
            "python_file.py": "import django",
        }
    )


@pytest.fixture
def project_with_multiple_python_files(write_tmp_files):
    return write_tmp_files(
        {
            "requirements.txt": """\
                pandas
                click
                """,
            "python_file.py": "import django",
            "subdir/python_file2.py": "import pandas",
            "subdir/python_file3.py": "import click",
            "subdir2/python_file4.py": "import notimported",
        }
    )


@pytest.fixture
def project_with_code_and_requirements_txt(write_tmp_files):
    def _inner(*, imports: Iterable[str], declares: Iterable[str]):
        code = "".join(f"import {s}\n" for s in imports)
        requirements = "".join(f"{s}\n" for s in declares)
        return write_tmp_files(
            {
                "code.py": code,
                "requirements.txt": requirements,
            }
        )

    return _inner


@pytest.fixture
def setup_fawltydeps_config(write_tmp_files):
    """Write a custom tmp_path/pyproject.toml with a [tool.fawltydeps] section.

    Write the given dict as config directives inside the [tool.fawltydeps]
    section. If a string is given instead of a dict, then write a pyproject.toml
    with that string (no automatic [tool.fawltydeps] section).
    """

    def _inner(contents: Union[str, TomlData]):
        if isinstance(contents, dict):
            header = ["[tool.fawltydeps]\n"]
            entries = []
            for k, v in contents.items():
                if isinstance(v, dict):
                    entries += [f"[tool.fawltydeps.{k}]\n"] + [
                        f"{kk} = {vv!r}\n" for kk, vv in v.items()
                    ]
                else:
                    entries += [f"{k} = {v!r}\n"]
            contents = "".join(header + entries)
        tmp_path = write_tmp_files({"pyproject.toml": contents})
        return tmp_path / "pyproject.toml"

    return _inner
