"""Fixtures for tests."""

import venv
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile, mkdtemp
from textwrap import dedent
from typing import Optional, Union

import pytest

from fawltydeps.types import TomlData
from fawltydeps.utils import site_packages

from .project_helpers import TarballPackage


@pytest.fixture
def inside_tmp_path(monkeypatch, tmp_path):
    """Convenience fixture to run a test with CWD set to tmp_path.

    This allows a test to run as if FalwtyDeps was invoked inside the temporary
    scratch directory. Allows testing of relative paths (inside tmp_path) that
    are closer to how most users run FawltyDeps inside their own projects.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


# The following weird params syntax applies the "needs_network" mark to all
# tests using this fixture. See https://github.com/pytest-dev/pytest/issues/1368
@pytest.fixture(params=[pytest.param(0, marks=pytest.mark.needs_network)])
def local_pypi(request, monkeypatch):
    cache_dir = TarballPackage.cache_dir(request.config.cache)
    TarballPackage.get_tarballs(request.config.cache)
    # Make sure we install from the local repo, and not from PyPI.
    # This goes for both the uv and pip install methods.

    # uv does not (yet) allow this to be configured via the environment, so we
    # need to go via a temporary config file:
    tmp_uv_config = NamedTemporaryFile("wt", delete=False, suffix=".toml")  # noqa: SIM115
    try:
        tmp_uv_config.write(
            dedent(f"""
                [pip]
                no-index = true
                find-links = ["{Path(cache_dir).as_posix()}"]
            """)
        )
        tmp_uv_config.close()

        # Point uv to the temporary config file
        monkeypatch.setenv("UV_CONFIG_FILE", tmp_uv_config.name)

        # pip is configured via these env vars
        monkeypatch.setenv("PIP_NO_INDEX", "True")
        monkeypatch.setenv("PIP_FIND_LINKS", str(cache_dir))

        yield  # Test code runs here
    finally:  # Clean up temporary file afterwards
        Path(tmp_uv_config.name).unlink()


@pytest.fixture
def write_tmp_files(tmp_path: Path):
    def _inner(file_contents: dict[str, Union[str, bytes]]) -> Path:
        for filename, contents in file_contents.items():
            path = tmp_path / filename
            assert path.relative_to(tmp_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(contents, bytes):
                path.write_bytes(contents)
            else:
                path.write_text(dedent(contents))
        return tmp_path

    return _inner


@pytest.fixture
def fake_venv(tmp_path):
    def create_one_fake_venv(
        fake_packages: dict[str, set[str]], *, venv_dir: Optional[Path] = None
    ) -> tuple[Path, Path]:
        if venv_dir is None:
            venv_dir = Path(mkdtemp(prefix="fake_venv.", dir=tmp_path))
        else:
            venv_dir.parent.mkdir(parents=True, exist_ok=True)
        venv.create(venv_dir, with_pip=False)

        site_dir = site_packages(venv_dir)
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
    fake_venv: Callable[[dict[str, set[str]]], tuple[Path, Path]], monkeypatch
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

    def inner(fake_packages: dict[str, set[str]]) -> Path:
        _venv_dir, package_dir = fake_venv(fake_packages)
        monkeypatch.syspath_prepend(package_dir)
        return package_dir

    return inner


@pytest.fixture
def fake_project(write_tmp_files, fake_venv):  # noqa: C901
    """Create a temporary Python project with the given contents/properties.

    This is a generalized helper to create the directory structure and file
    contents that reflect a Python project containing the imports, declared
    dependencies and Python environments passed as arguments. The allowed
    arguments are:

    - imports: a list of strings (import names) that will be written as import
        statements (one line per item) into a file called code.py.
    - declared_deps: a list of strings (PEP 508 requirements specifiers) that
        will be written (one line per item) into a requirements.txt file.
    - fake_venvs: a dict mapping strings (virtualenv paths) to nested dicts to
        be passed to fake_venv() (i.e. each nested dict maps dependency names
        to lists of provided import names for that fake_venv instance).
    - files_with_imports: a dict mapping strings (filenames) to lists of strings
        (imports); multiple files will be written, each in the same manner as
         described in 'imports' above.
    - files_with_declared_deps: a dict mapping strings (filenames) to either:
          - lists of strings (deps), or to
          - a pair consisting of a list of strings (deps) and a dict of names to
            lists of strings (extras/optional deps).
        The dependencies will be written into associated files, formatted
        according to the filenames (must be one of requirements.txt, setup.py,
        setup.cfg, pyproject.toml, pixi.toml, or environment.yml).
    - extra_file_contents: a dict with extra files and their associated contents
        to be forwarded directly to write_tmp_files().

    Returns tmp_path, which is regarded as the root directory of the temporary
    Python project.
    """
    Imports = list[str]
    Deps = list[str]
    ExtraDeps = dict[str, Deps]

    def format_python_code(imports: Imports) -> str:
        return "".join(f"import {s}\n" for s in imports)

    def format_requirements_txt(deps: Deps, no_extras: ExtraDeps) -> str:
        assert not no_extras  # not supported
        return "".join(f"{s}\n" for s in deps)

    def format_setup_py(deps: Deps, extras: ExtraDeps) -> str:
        return f"""\
            from setuptools import setup

            setup(
                name="MyLib",
                install_requires={deps!r},
                extras_require={extras!r}
            )
            """

    def format_setup_cfg(deps: Deps, no_extras: ExtraDeps) -> str:
        assert not no_extras  # not supported
        return dedent(
            """\
                [metadata]
                name = "MyLib"

                [options]
                install_requires =
                """
        ) + "\n".join(f"    {d}" for d in deps)

    def format_pyproject_toml(deps: Deps, extras: ExtraDeps) -> str:
        return dedent(
            f"""\
                [project]
                name = "MyLib"

                dependencies = {deps!r}

                [project.optional-dependencies]
                """
        ) + "\n".join(f"{k} = {v!r}" for k, v in extras.items())

    def format_pixi_toml(deps: Deps, extras: ExtraDeps) -> str:
        ret = dedent(
            """\
                [project]
                name = "MyLib"

                [dependencies]
                """
        ) + "\n".join(f'{dep} = "*"' for dep in deps)
        for feature, extra_deps in extras.items():
            ret += f"\n[feature.{feature}.dependencies]\n"
            ret += "\n".join(f'{dep} = "*"' for dep in extra_deps)
        return ret

    def format_environment_yml(deps: Deps, no_extras: ExtraDeps) -> str:
        assert not no_extras  # not supported
        return dedent(
            """\
                name: MyLib

                dependencies:
                """
        ) + "".join(f"  - {dep}\n" for dep in deps)

    def format_deps(
        filename: str, all_deps: Union[Deps, tuple[Deps, ExtraDeps]]
    ) -> str:
        if isinstance(all_deps, tuple):
            deps, extras = all_deps
        else:
            deps, extras = all_deps, {}
        formatters: dict[str, Callable[[Deps, ExtraDeps], str]] = {
            "requirements.txt": format_requirements_txt,  # default choice
            "setup.py": format_setup_py,
            "setup.cfg": format_setup_cfg,
            "pyproject.toml": format_pyproject_toml,
            "pixi.toml": format_pixi_toml,
            "environment.yml": format_environment_yml,
        }
        formatter = formatters.get(Path(filename).name, format_requirements_txt)
        return formatter(deps, extras)

    def create_one_fake_project(
        *,
        imports: Optional[Imports] = None,
        declared_deps: Optional[Deps] = None,
        fake_venvs: Optional[dict[str, dict[str, set[str]]]] = None,
        files_with_imports: Optional[dict[str, Imports]] = None,
        files_with_declared_deps: Optional[
            dict[str, Union[Deps, tuple[Deps, ExtraDeps]]]
        ] = None,
        extra_file_contents: Optional[dict[str, str]] = None,
    ) -> Path:
        tmp_files = {}
        if imports is not None:
            tmp_files["code.py"] = format_python_code(imports)
        if declared_deps is not None:
            tmp_files["requirements.txt"] = format_requirements_txt(declared_deps, {})
        if files_with_imports is not None:
            for filename, per_file_imports in files_with_imports.items():
                tmp_files[filename] = format_python_code(per_file_imports)
        if files_with_declared_deps is not None:
            for filename, all_deps in files_with_declared_deps.items():
                tmp_files[filename] = format_deps(filename, all_deps)
        if extra_file_contents is not None:
            tmp_files.update(extra_file_contents)
        tmp_path: Path = write_tmp_files(tmp_files)
        if fake_venvs is not None:
            for venv_dir, fake_packages in fake_venvs.items():
                fake_venv(fake_packages, venv_dir=tmp_path / venv_dir)
        return tmp_path

    return create_one_fake_project


@pytest.fixture
def project_with_setup_and_requirements(fake_project):
    return fake_project(
        files_with_declared_deps={
            "requirements.txt": ["pandas", "click"],
            "subdir/requirements.txt": ["pandas", "tensorflow>=2"],
            "setup.py": (
                ["pandas", "click>=1.2"],  # install_requires
                {"annoy": ["annoy==1.15.2"], "chinese": ["jieba"]},  # extras_require
            ),
        },
        files_with_imports={"python_file.py": ["django"]},
    )


@pytest.fixture
def project_with_setup_with_cfg_pyproject_and_requirements(fake_project):
    return fake_project(
        files_with_declared_deps={
            "requirements.txt": ["pandas", "click"],
            "subdir/dev-requirements.txt": ["black"],
            "subdir/requirements.txt": ["pandas", "tensorflow>=2"],
            "subdir/requirements-docs.txt": ["sphinx"],
            "setup.cfg": ["dependencyA", "dependencyB"],  # install_requires
            "pyproject.toml": (
                ["pandas", "pydantic>1.10.4"],  # dependencies
                {"dev": ["pylint >= 2.15.8"]},  # optional-dependencies
            ),
        },
        extra_file_contents={
            "setup.py": """\
                from setuptools import setup

                setup(use_scm_version=True)
                """,
        },
        files_with_imports={"python_file.py": ["django"]},
    )


@pytest.fixture
def project_with_multiple_python_files(fake_project):
    return fake_project(
        declared_deps=["pandas", "click"],
        files_with_imports={
            "python_file.py": ["django"],
            "subdir/python_file2.py": ["pandas"],
            "subdir/python_file3.py": ["click"],
            "subdir2/python_file4.py": ["notimported"],
        },
    )


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
