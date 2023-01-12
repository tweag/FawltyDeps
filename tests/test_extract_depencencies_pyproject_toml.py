"""Test extracting dependencies from pyproject.toml"""
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
