"""Test that we can extract dependencies from requirement.txt and other files"""
from pathlib import Path
from textwrap import dedent

import pytest

from fawltydeps.extract_dependencies import (
    extract_dependencies,
    parse_requirements_contents,
)


@pytest.mark.parametrize(
    "file_content,file_name,expected",
    [
        pytest.param(
            dedent(
                """\
                pandas
                click
                """
            ),
            Path("requirements.txt"),
            [("pandas", Path("requirements.txt")), ("click", Path("requirements.txt"))],
            id="__simple_requirements_success",
        ),
        pytest.param(
            dedent(
                """\
                pandas

                click >=1.2
                """
            ),
            Path("requirements.txt"),
            [("pandas", Path("requirements.txt")), ("click", Path("requirements.txt"))],
            id="__requirements_with_versions__yields_names",
        ),
    ],
)
def test_parse_requirements_contents(file_content, file_name, expected):

    result = list(parse_requirements_contents(file_content, file_name))
    assert result == expected


def test_extract_dependencies__simple_project__returns_list(simple_project):

    expect = ["pandas", "click", "pandas", "tensorflow"]
    assert [a for (a, _) in extract_dependencies(simple_project)] == expect
