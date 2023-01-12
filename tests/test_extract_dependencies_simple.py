"""Test that dependencies are parsed from requirements files"""
import logging
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
    assert sorted(result) == sorted(expected)


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
            id="__simple_requirements_in_setup_py__succeeds",
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

                def myfunc():
                    def setup(**kwargs):
                        pass
                    setup(
                        name="IncorrectCall",
                        install_requires=["foo"]
                    )

                setup(
                    name="MyLib",
                    version=random_version(),
                    install_requires=["pandas", "click>=1.2"]
                )

                """
            ),
            Path("setup.py"),
            [("pandas", Path("setup.py")), ("click", Path("setup.py"))],
            id="__two_setup_calls__uses_only_top_level",
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
    assert sorted(result) == sorted(expected)


def test_parse_setup_contents__cannot_parse_install_requires__logs_warning(caplog):
    setup_contents = dedent(
        """\
        from setuptools import setup

        generate_requirements = lambda n: [f"mock-requirement-{k}" for k in range(n)]
        setup(
            name="MyLib",
            install_requires=generate_requirements(4)
        )
        """
    )
    expected = []
    caplog.set_level(logging.WARNING)
    result = list(parse_setup_contents(setup_contents, ""))
    assert "Could not parse contents of `install_requires`" in caplog.text
    assert expected == result


def test_parse_setup_contents__cannot_parse_extras_require__logs_warning(caplog):
    setup_contents = dedent(
        """\
        from setuptools import setup

        generate_requirements = lambda n: {f"extra{k}": f"mock-requirement-{k}" for k in range(n)}
        setup(
            name="MyLib",
            extras_require=generate_requirements(4)
        )
        """
    )
    expected = []
    caplog.set_level(logging.WARNING)
    result = list(parse_setup_contents(setup_contents, ""))
    assert "Could not parse contents of `extras_require`" in caplog.text
    assert expected == result


def test_parse_setup_contents__cannot_parse_extras_require_value__logs_warning(caplog):
    setup_contents = dedent(
        """\
        from setuptools import setup

        generate_requirements = lambda n: [f"mock-requirement-{k}" for k in range(n)]
        setup(
            name="MyLib",
            extras_require={
                "simple_parsing":["abc"],
                "complex_parsing": generate_requirements(3)
                }
        )
        """
    )
    expected = [("abc", "")]
    caplog.set_level(logging.WARNING)
    result = list(parse_setup_contents(setup_contents, ""))
    assert "Could not parse contents of `extras_require`" in caplog.text
    assert expected == result


def test_parse_setup_contents__multiple_entries_in_extras_require__returns_list():
    setup_contents = dedent(
        """\
        from setuptools import setup

        setup(
            name="MyLib",
            extras_require={
                "simple_parsing":["abc"],
                "bert": [
                    "bert-serving-server>=1.8.6",
                    "bert-serving-client>=1.8.6",
                    "pytorch-transformer",
                    "flair"
                    ],
                }
        )
        """
    )
    expected = [
        ("abc", ""),
        ("bert-serving-server", ""),
        ("bert-serving-client", ""),
        ("pytorch-transformer", ""),
        ("flair", ""),
    ]
    result = list(parse_setup_contents(setup_contents, ""))
    assert sorted(expected) == sorted(result)


def test_extract_dependencies__simple_project__returns_list(project_with_requirements):
    expect = ["pandas", "click", "pandas", "tensorflow"]
    assert sorted(
        [a for (a, _) in extract_dependencies(project_with_requirements)]
    ) == sorted(expect)


def test_extract_dependencies__project_with_requirements_and_setup__returns_list(
    project_with_setup_and_requirements,
):
    expect = [
        "pandas",
        "click",
        "pandas",
        "click",
        "annoy",
        "jieba",
        "pandas",
        "tensorflow",
    ]
    assert sorted(
        [a for (a, _) in extract_dependencies(project_with_setup_and_requirements)]
    ) == sorted(expect)


def test_extract_dependencies__parse_only_requirements_from_subdir__returns_list(
    project_with_setup_and_requirements,
):
    "In setup.py requirements are read from dict."
    expect = [
        "pandas",
        "tensorflow",
    ]
    path = project_with_setup_and_requirements / "subdir/requirements.txt"
    actual = [dep for (dep, _) in extract_dependencies(path)]
    assert sorted(actual) == sorted(expect)


def test_extract_dependencies__unsupported_file__raises_error(
    project_with_setup_and_requirements, caplog
):
    "In setup.py requirements are read from dict."
    caplog.set_level(logging.WARNING)
    list(
        extract_dependencies(
            project_with_setup_and_requirements.joinpath("python_file.py")
        )
    )
    assert "Parsing file python_file.py is not supported" in caplog.text


def test_extract_dependencies__project_with_pyproject_setup_and_requirements__returns_list(
    project_with_setup_pyproject_and_requirements,
):
    expect = [
        "pandas",
        "click",
        "pandas",
        "click",
        "annoy",
        "jieba",
        "pandas",
        "tensorflow",
        "pandas",
        "pydantic",
        "pylint",
    ]
    assert sorted(
        [
            a
            for (a, _) in extract_dependencies(
                project_with_setup_pyproject_and_requirements
            )
        ]
    ) == sorted(expect)


def test_extract_dependencies__project_with_pyproject__returns_list(
    project_with_pyproject,
):
    expect = [
        "pandas",
        "pydantic",
        "pylint",
    ]
    assert sorted(
        [a for (a, _) in extract_dependencies(project_with_pyproject)]
    ) == sorted(expect)
