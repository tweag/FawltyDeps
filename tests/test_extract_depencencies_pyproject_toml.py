"""Test extracting dependencies from pyproject.toml"""
import logging
from pathlib import Path
from textwrap import dedent

from fawltydeps.extract_dependencies import parse_pyproject_contents


def test_parse_pyproject_content__poetry_main_dependencies__yields_dependencies():
    filename = Path("pyproject.toml")
    pyproject_toml = dedent(
        """\
            [tool.poetry]

            [tool.poetry.dependencies]
            python = "^3.8"
            isort = "^5.10"
            tomli = "^2.0.1"
        """
    )
    result = list(parse_pyproject_contents(pyproject_toml, filename))
    expected = [(dep, filename) for dep in ["isort", "tomli"]]
    assert result == expected


def test_parse_pyproject_content__poetry_groups__yields_dependencies():
    filename = Path("pyproject.toml")
    pyproject_toml = dedent(
        """\
            [tool.poetry]

            [tool.poetry.group.dev.dependencies]
            black = "^22"
            mypy = "^0.991"

            [tool.poetry.group.test.dependencies]
            pytest = "^5.0.0"
        """
    )
    result = list(parse_pyproject_contents(pyproject_toml, filename))
    expected = [(dep, filename) for dep in ["black", "mypy", "pytest"]]
    assert result == expected


def test_parse_pyproject_content__poetry_extras__yields_dependencies():
    filename = Path("pyproject.toml")
    pyproject_toml = dedent(
        """\
            [tool.poetry]

            [tool.poetry.extras]
            test = ["pytest < 5.0.0", "pytest-cov[all]"]
            dev = ["pylint >= 2.15.8"]
        """
    )
    result = list(parse_pyproject_contents(pyproject_toml, filename))
    expected = [(dep, filename) for dep in ["pytest", "pytest-cov", "pylint"]]
    assert result == expected


def test_parse_pyproject_content__poetry_main_group_and_extra_dependencies__yields_dependencies():
    filename = Path("pyproject.toml")
    pyproject_toml = dedent(
        """\
            [tool.poetry]

            [tool.poetry.dependencies]
            python = "^3.8"
            isort = "^5.10"
            tomli = "^2.0.1"

            [tool.poetry.group.dev.dependencies]
            black = "^22"
            mypy = "^0.991"

            [tool.poetry.group.experimental.dependencies]
            django = "^2.1"

            [tool.poetry.extras]
            test = ["pytest < 5.0.0", "pytest-cov[all]"]
            dev = ["pylint >= 2.15.8"]
        """
    )
    result = list(parse_pyproject_contents(pyproject_toml, filename))
    expected = [
        (dep, filename)
        for dep in [
            "isort",
            "tomli",
            "black",
            "mypy",
            "django",
            "pytest",
            "pytest-cov",
            "pylint",
        ]
    ]
    assert result == expected


def test_parse_pyproject_content__dependencies_field__yields_dependencies():
    filename = Path("pyproject.toml")
    pyproject_toml = dedent(
        """\
            [project]
            name = "fawltydeps"

            dependencies = ["isort", "django>2.1; os_name != 'nt'"]
        """
    )
    result = list(parse_pyproject_contents(pyproject_toml, filename))
    expected = [(dep, filename) for dep in ["isort", "django"]]
    assert result == expected


def test_parse_pyproject_content__optional_dependencies_field__yields_dependencies():
    filename = Path("pyproject.toml")
    pyproject_toml = dedent(
        """\
            [project]

            [project.optional-dependencies]
            test = ["pytest < 5.0.0", "pytest-cov[all]"]
            dev = ["pylint >= 2.15.8"]

        """
    )
    result = list(parse_pyproject_contents(pyproject_toml, filename))
    expected = [(dep, filename) for dep in ["pytest", "pytest-cov", "pylint"]]
    assert result == expected


def test_parse_pyproject_content__main_and_optional_dependencies__yields_dependencies():
    filename = Path("pyproject.toml")
    pyproject_toml = dedent(
        """\
            [project]
            name = "fawltydeps"

            dependencies = ["isort", "django>2.1; os_name != 'nt'"]

            [project.optional-dependencies]
            test = ["pytest < 5.0.0", "pytest-cov[all]"]
            dev = ["pylint >= 2.15.8"]

        """
    )
    result = list(parse_pyproject_contents(pyproject_toml, filename))
    expected = [
        (dep, filename) for dep in ["isort", "django", "pytest", "pytest-cov", "pylint"]
    ]
    assert result == expected


def test_parse_pyproject_content__poetry_and_pep621_all_metadata_fields_yields_dependencies():
    filename = Path("pyproject.toml")
    pyproject_toml = dedent(
        """\
            [project]
            name = "fawltydeps"

            dependencies = ["pandas", "pydantic>1.10.4"]

            [project.optional-dependencies]
            dev = ["pylint >= 2.15.8"]

            [tool.poetry]
            [tool.poetry.dependencies]
            python = "^3.8"
            isort = "^5.10"
            tomli = "^2.0.1"

            [tool.poetry.group.dev.dependencies]
            black = "^22"
            mypy = "^0.991"

            [tool.poetry.group.experimental.dependencies]
            django = "^2.1"

            [tool.poetry.extras]
            alpha = ["pytorch < 1.12.1", "numpy >= 1.17.2"]
            dev = ["flake >= 5.0.1"]
        """
    )
    result = list(parse_pyproject_contents(pyproject_toml, filename))
    expected = [
        (dep, filename)
        for dep in [
            "pandas",
            "pydantic",
            "pylint",
            "isort",
            "tomli",
            "black",
            "mypy",
            "django",
            "pytorch",
            "numpy",
            "flake",
        ]
    ]
    assert result == expected


def test_parse_pyproject_contents__cannot_find_dependencies__logs_debug_message(
    caplog, tmp_path
):
    pyproject_contents = dedent(
        """\
            [project]
            name = "fawltydeps"

        """
    )
    expected = []
    caplog.set_level(logging.DEBUG)
    path_hint = tmp_path / "pyproject.toml"
    result = list(parse_pyproject_contents(pyproject_contents, path_hint))
    assert f"Failed to find PEP621 dependencies in {path_hint}" in caplog.text
    assert f"No PEP621 optional dependencies found in {path_hint}" in caplog.text
    assert expected == result


def test_parse_pyproject_contents__cannot_find_poetry_dependencies__logs_debug_message(
    caplog, tmp_path
):
    pyproject_contents = dedent(
        """\
            [tool.poetry]
            name = "fawltydeps"

        """
    )
    expected = []
    caplog.set_level(logging.DEBUG)
    path_hint = tmp_path / "pyproject.toml"
    result = list(parse_pyproject_contents(pyproject_contents, path_hint))
    assert f"Failed to find PEP621 dependencies in {path_hint}" in caplog.text
    assert f"No PEP621 optional dependencies found in {path_hint}" in caplog.text
    assert f"Failed to find Poetry dependencies in {path_hint}" in caplog.text
    assert f"No Poetry grouped dependencies found in {path_hint}" in caplog.text
    assert f"No Poetry extra dependencies found in {path_hint}" in caplog.text
    assert expected == result
