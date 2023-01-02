"""Test extracting dependencies from pyproject.toml"""
from pathlib import Path
from textwrap import dedent

import pytest

from fawltydeps.extract_dependencies import (
    extract_dependencies,
    parse_pyproject_contents,
)


def test_parse_pyproject_content__poetry_project__yields_dependencies():

    filename = "pyproject.toml"
    pyproject_toml = dedent(
        """\
            [tool.poetry]
            name = "fawltydeps"

            [tool.poetry.scripts]
            fawltydeps = "fawltydeps.main:main"

            [tool.poetry.dependencies]
            python = "^3.8"
            isort = "^5.10"
            black = "^22"
            pytest = "^7.1.0"
            mypy = "^0.991"
            pylint = "^2.15.8"
            types-setuptools = "^65.6.0.2"
            tomli = "^2.0.1"
        """
    )
    result = list(parse_pyproject_contents(pyproject_toml, filename))
    expected = list(
        zip(
            [
                "isort",
                "black",
                "pytest",
                "mypy",
                "pylint",
                "types-setuptools",
                "tomli",
            ],
            ["pyproject.toml"] * 7,
        )
    )
    assert result == expected
