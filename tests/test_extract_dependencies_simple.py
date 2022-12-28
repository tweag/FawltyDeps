"""Test that we can extract dependencies from requirement.txt and other files"""
from pathlib import Path
from textwrap import dedent

import pytest

from fawltydeps.extract_dependencies import (
    extract_dependencies,
    parse_requirements_contents,
    parse_setup_contents,
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


@pytest.mark.parametrize(
    "file_content,file_name,expected",
    [
        pytest.param(
            dedent(
                """\
                from setuptools import setup

                setup(
                    name="MyLib",
                    install_requires=["pandas", "click"]
                )
                """
            ),
            Path("setup.py"),
            [("pandas", Path("setup.py")), ("click", Path("setup.py"))],
            id="__simple_requirements_in_setup_success",
        ),
        pytest.param(
            dedent(
                """\
                from setuptools import setup

                setup(
                    name="MyLib",
                    install_requires=["pandas", "click>=1.2"]
                )
                """
            ),
            Path("setup.py"),
            [("pandas", Path("setup.py")), ("click", Path("setup.py"))],
            id="__requirements_with_versions__yields_names",
        ),
        pytest.param(
            dedent(
                """\
                from setuptools import setup

                setup(
                    name="MyLib"
                )
                """
            ),
            Path("setup.py"),
            [],
            id="__no_requirements__yields_nothing",
        ),
        pytest.param(
            dedent(
                """\
                from setuptools import setup

                def random_version():
                    return 42

                setup(
                    name="MyLib",
                    version=random_version(),
                    install_requires=["pandas", "click>=1.2"]
                )
                """
            ),
            Path("setup.py"),
            [("pandas", Path("setup.py")), ("click", Path("setup.py"))],
            id="__handles_nested_functions__yields_names",
        ),
        pytest.param(
            dedent(
                """\
                from setuptools import setup

                setup(
                    name="MyLib",
                    version=random_version(),
                    install_requires=["pandas", "click>=1.2"]
                )

                setup(
                    name="IncorrectCall",
                    install_requires=["foo"]
                )
                """
            ),
            Path("setup.py"),
            [("pandas", Path("setup.py")), ("click", Path("setup.py"))],
            id="__two_setup_calls__uses_only_first",
        ),
        pytest.param(
            dedent(
                """\
                from setuptools import setup

                setup(
                    name="MyLib",
                    extras_require={
                        'annoy': ['annoy==1.15.2'],
                        'chinese': ['jieba']
                        }
                )
                """
            ),
            Path("setup.py"),
            [("annoy", Path("setup.py")), ("jieba", Path("setup.py"))],
            id="__extras_present__yields_names",
        ),
        pytest.param(
            dedent(
                """\
                from setuptools import setup

                setup(
                    name="MyLib",
                    install_requires=["pandas", "click>=1.2"],
                    extras_require={
                        'annoy': ['annoy==1.15.2'],
                        'chinese': ['jieba']
                        }
                )
                """
            ),
            Path("setup.py"),
            [
                ("pandas", Path("setup.py")),
                ("click", Path("setup.py")),
                ("annoy", Path("setup.py")),
                ("jieba", Path("setup.py")),
            ],
            id="__extras_and_regular_dependencies__yields_all_names",
        ),
    ],
)
def test_parse_setup_contents(file_content, file_name, expected):

    result = list(parse_setup_contents(file_content, file_name))
    assert result == expected


def test_extract_dependencies__simple_project__returns_list(simple_project):

    expect = ["pandas", "click", "pandas", "tensorflow"]
    assert [a for (a, _) in extract_dependencies(simple_project)] == expect
