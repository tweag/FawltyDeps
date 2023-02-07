"""Test that dependencies are parsed from requirements files"""
import logging
from pathlib import Path
from textwrap import dedent
from typing import List

import pytest

from fawltydeps.extract_declared_dependencies import (
    extract_declared_dependencies,
    parse_requirements_contents,
    parse_setup_cfg_contents,
    parse_setup_contents,
)
from fawltydeps.types import DeclaredDependency, Location


def dependency_factory(data: List[str], path: str) -> List[DeclaredDependency]:
    return [DeclaredDependency(d, Location(Path(path))) for d in data]


@pytest.mark.parametrize(
    "file_content,expected",
    [
        pytest.param(
            dedent(
                """\
                pandas
                click
                """
            ),
            dependency_factory(
                ["pandas", "click"],
                "requirements.txt",
            ),
            id="__simple_requirements_success",
        ),
        pytest.param(
            dedent(
                """\
                pandas

                click >=1.2
                """
            ),
            dependency_factory(
                ["pandas", "click"],
                "requirements.txt",
            ),
            id="__requirements_with_versions__yields_names",
        ),
    ],
)
def test_parse_requirements_contents(file_content, expected):
    source = Location(Path("requirements.txt"))
    result = list(parse_requirements_contents(file_content, source))
    assert sorted(result) == sorted(expected)


@pytest.mark.parametrize(
    "file_content,expected",
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
            dependency_factory(["pandas", "click"], "setup.py"),
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
            dependency_factory(["pandas", "click"], "setup.py"),
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
            dependency_factory(["pandas", "click"], "setup.py"),
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
            dependency_factory(["pandas", "click"], "setup.py"),
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
            dependency_factory(["annoy", "jieba"], "setup.py"),
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
            dependency_factory(["pandas", "click", "annoy", "jieba"], "setup.py"),
            id="__extras_and_regular_dependencies__yields_all_names",
        ),
    ],
)
def test_parse_setup_contents(file_content, expected):
    source = Location(Path("setup.py"))
    result = list(parse_setup_contents(file_content, source))
    assert sorted(result) == sorted(expected)


@pytest.mark.parametrize(
    "file_content,expected",
    [
        pytest.param(
            dedent(
                """\
                [options]
                install_requires =
                    pandas
                    click
                """
            ),
            dependency_factory(["pandas", "click"], "setup.cfg"),
            id="__simple_requirements_in_setup_cfg__succeeds",
        ),
        pytest.param(
            dedent(
                """\
                [metadata]
                license_files = LICENSE
                """
            ),
            [],
            id="__no_requirements_in_setup_cfg__returns_none",
        ),
        pytest.param(
            dedent(
                """\
                [options.extras_require]
                test = pytest
                """
            ),
            [DeclaredDependency("pytest", Location(Path("setup.cfg")))],
            id="__extra_requirements_section_in_setup_cfg__succeeds",
        ),
        pytest.param(
            dedent(
                """\
                [options.tests_require]
                test = pytest
                """
            ),
            [DeclaredDependency("pytest", Location(Path("setup.cfg")))],
            id="__tests_requirements_section_in_setup_cfg__succeeds",
        ),
        pytest.param(
            dedent(
                """\
                [options]
                tests_require =
                    hypothesis
                    tox
                """
            ),
            dependency_factory(["hypothesis", "tox"], "setup.cfg"),
            id="__tests_requirements_in_setup_cfg__succeeds",
        ),
        pytest.param(
            dedent(
                """\
                [options]
                extras_require =
                    hypothesis
                    tox
                """
            ),
            dependency_factory(["hypothesis", "tox"], "setup.cfg"),
            id="__extras_requirements_in_setup_cfg__succeeds",
        ),
        pytest.param(
            dedent(
                """\
                [options]
                install_requires =
                    pandas
                    click
                tests_require =
                    tox
                extras_require =
                    scipy

                [options.extras_require]
                test = pytest

                [options.tests_require]
                test = hypothesis
                """
            ),
            dependency_factory(
                ["pandas", "click", "tox", "scipy", "pytest", "hypothesis"], "setup.cfg"
            ),
            id="__all_requirements_types_in_setup_cfg__succeeds",
        ),
    ],
)
def test_parse_setup_cfg_contents(file_content, expected):
    source = Location(Path("setup.cfg"))
    result = list(parse_setup_cfg_contents(file_content, source))
    assert sorted(result) == sorted(expected)


def test_parse_setup_contents__cannot_parse_install_requires__logs_warning(
    tmp_path, caplog
):
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
    setup_path = tmp_path / "setup.py"
    result = list(parse_setup_contents(setup_contents, Location(setup_path)))
    assert "Could not parse contents of `install_requires`:" in caplog.text
    assert str(setup_path) in caplog.text
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
    result = list(parse_setup_contents(setup_contents, Location(Path(""))))
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
    expected = [DeclaredDependency("abc", Location(Path("")))]
    caplog.set_level(logging.WARNING)
    result = list(parse_setup_contents(setup_contents, Location(Path(""))))
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
    expected = dependency_factory(
        [
            "abc",
            "bert-serving-server",
            "bert-serving-client",
            "pytorch-transformer",
            "flair",
        ],
        Path(""),
    )
    result = list(parse_setup_contents(setup_contents, Location(Path(""))))
    assert sorted(expected) == sorted(result)


def test_extract_declared_dependencies__simple_project__returns_list(
    project_with_requirements,
):
    expect = ["pandas", "click", "pandas", "tensorflow"]
    assert sorted(
        [a for (a, _) in extract_declared_dependencies(project_with_requirements)]
    ) == sorted(expect)


def test_extract_declared_dependencies__project_with_requirements_and_setup__returns_list(
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
        [
            a
            for (a, _) in extract_declared_dependencies(
                project_with_setup_and_requirements
            )
        ]
    ) == sorted(expect)


def test_extract_declared_dependencies__parse_only_requirements_from_subdir__returns_list(
    project_with_setup_and_requirements,
):
    "In setup.py requirements are read from dict."
    expect = [
        "pandas",
        "tensorflow",
    ]
    path = project_with_setup_and_requirements / "subdir/requirements.txt"
    actual = [dep for (dep, _) in extract_declared_dependencies(path)]
    assert sorted(actual) == sorted(expect)


def test_extract_declared_dependencies__project_with_pyproject_setup_and_requirements__returns_list(
    project_with_setup_pyproject_and_requirements,
):
    expect = [
        # from requirements.txt:
        "pandas",
        "click",
        # from setup.py:
        "pandas",
        "click",
        "annoy",
        "jieba",
        # from subdir/requirements.txt:
        "pandas",
        "tensorflow",
        # from pyproject.toml:
        "pandas",
        "pydantic",
        "pylint",
    ]
    assert sorted(
        [
            a
            for (a, _) in extract_declared_dependencies(
                project_with_setup_pyproject_and_requirements
            )
        ]
    ) == sorted(expect)


def test_extract_declared_dependencies__project_with_pyproject__returns_list(
    project_with_pyproject,
):
    expect = [
        "pandas",
        "pydantic",
        "pylint",
    ]
    assert sorted(
        [a for (a, _) in extract_declared_dependencies(project_with_pyproject)]
    ) == sorted(expect)


def test_extract_declared_dependencies__project_with_setup_cfg__returns_list(
    project_with_setup_cfg,
):
    expect = [
        "pandas",
        "django",
    ]
    assert sorted(
        [a for (a, _) in extract_declared_dependencies(project_with_setup_cfg)]
    ) == sorted(expect)


def test_extract_declared_dependencies__project_with_setup_cfg_pyproject_requirements__returns_list(
    project_with_setup_with_cfg_pyproject_and_requirements,
):
    expect = [
        # from requirements.txt:
        "pandas",
        "click",
        # from setup.py:
        # from setup.cfg:
        "dependencya",
        "dependencyb",
        # from subdir/requirements.txt:
        "pandas",
        "tensorflow",
        # from pyproject.toml:
        "pandas",
        "pydantic",
        "pylint",
    ]
    actual = list(
        extract_declared_dependencies(
            project_with_setup_with_cfg_pyproject_and_requirements
        )
    )
    assert sorted([a for (a, _) in actual]) == sorted(expect)
