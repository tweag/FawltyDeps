"""Test that dependencies are parsed from requirements files"""
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
            """\
            pandas
            click
            """,
            dependency_factory(
                ["pandas", "click"],
                "requirements.txt",
            ),
            id="__simple_requirements_success",
        ),
        pytest.param(
            """\
            pandas

            click >=1.2
            """,
            dependency_factory(
                ["pandas", "click"],
                "requirements.txt",
            ),
            id="__requirements_with_versions__yields_names",
        ),
        pytest.param(
            dedent(
                """\
                requests [security] @ https://github.com/psf/requests/archive/refs/heads/main.zip
                """
            ),
            dependency_factory(
                ["requests"],
                "requirements.txt",
            ),
            id="__requirements_with_url_based_specifier__yields_names",
        ),
        pytest.param(
            dedent(
                """\
                # this is a comment
                click >=1.2
                """
            ),
            dependency_factory(
                ["click"],
                "requirements.txt",
            ),
            id="__requirements_with_comment__ignores_comment",
        ),
        pytest.param(
            dedent(
                """\
                -e .
                click >=1.2
                """
            ),
            dependency_factory(
                ["click"],
                "requirements.txt",
            ),
            id="__requirements_with_option__ignores_option",
        ),
    ],
)
def test_parse_requirements_contents(file_content, expected):
    source = Location(Path("requirements.txt"))
    result = list(parse_requirements_contents(dedent(file_content), source))
    assert sorted(result) == sorted(expected)


@pytest.mark.parametrize(
    "file_content,expected",
    [
        pytest.param(
            """\
            from setuptools import setup

            setup(
                name="MyLib",
                install_requires=["pandas", "click"]
            )
            """,
            dependency_factory(["pandas", "click"], "setup.py"),
            id="__simple_requirements_in_setup_py__succeeds",
        ),
        pytest.param(
            """\
            from setuptools import setup

            setup(
                name="MyLib",
                install_requires=["pandas", "click>=1.2"]
            )
            """,
            dependency_factory(["pandas", "click"], "setup.py"),
            id="__requirements_with_versions__yields_names",
        ),
        pytest.param(
            """\
            from setuptools import setup

            setup(
                name="MyLib"
            )
            """,
            [],
            id="__no_requirements__yields_nothing",
        ),
        pytest.param(
            """\
            from setuptools import setup

            def random_version():
                return 42

            setup(
                name="MyLib",
                version=random_version(),
                install_requires=["pandas", "click>=1.2"]
            )
            """,
            dependency_factory(["pandas", "click"], "setup.py"),
            id="__handles_nested_functions__yields_names",
        ),
        pytest.param(
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
            """,
            dependency_factory(["pandas", "click"], "setup.py"),
            id="__two_setup_calls__uses_only_top_level",
        ),
        pytest.param(
            """\
            from setuptools import setup

            setup(
                name="MyLib",
                extras_require={
                    'annoy': ['annoy==1.15.2'],
                    'chinese': ['jieba']
                    }
            )
            """,
            dependency_factory(["annoy", "jieba"], "setup.py"),
            id="__extras_present__yields_names",
        ),
        pytest.param(
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
            """,
            dependency_factory(["pandas", "click", "annoy", "jieba"], "setup.py"),
            id="__extras_and_regular_dependencies__yields_all_names",
        ),
        pytest.param(
            """\
            from setuptools import setup

            my_deps = ["pandas", "click"]

            setup(
                name="MyLib",
                install_requires=my_deps,
            )
            """,
            dependency_factory(["pandas", "click"], "setup.py"),
            id="__direct_list_variable_reference__succeeds",
        ),
        pytest.param(
            """\
            from setuptools import setup

            my_extra_deps = {
                "annoy": ["annoy==1.15.2"],
                "chinese": ["jieba"],
            }

            setup(
                name="MyLib",
                extras_require=my_extra_deps,
            )
            """,
            dependency_factory(["annoy", "jieba"], "setup.py"),
            id="__direct_dict_variable_reference__succeeds",
        ),
        pytest.param(
            """\
            from setuptools import setup

            pandas = "pandas"
            click = "click"

            setup(
                name="MyLib",
                install_requires=[pandas, click],
            )
            """,
            dependency_factory(["pandas", "click"], "setup.py"),
            id="__variable_reference_inside_list__succeeds",
        ),
        pytest.param(
            """\
            from setuptools import setup

            annoy = "annoy"
            annoy_deps = ["annoy==1.15.2"]
            foobar = "foobar"

            setup(
                name="MyLib",
                extras_require={
                    annoy: annoy_deps,
                    foobar: [foobar],
                },
            )
            """,
            dependency_factory(["annoy", "foobar"], "setup.py"),
            id="__variable_reference_inside_dict__succeeds",
        ),
        pytest.param(
            """\
            from setuptools import setup

            pandas = "pandas"
            my_deps = [pandas, "click"]
            annoy = "annoy"
            annoy_deps = ["annoy==1.15.2"]
            foobar = "foobar"
            my_extra_deps = {
                annoy: annoy_deps,
                foobar: [foobar],
            }

            setup(
                name="MyLib",
                install_requires=my_deps,
                extras_require=my_extra_deps,
            )
            """,
            dependency_factory(["pandas", "click", "annoy", "foobar"], "setup.py"),
            id="__nested_variable_reference__succeeds",
        ),
    ],
)
def test_parse_setup_contents(file_content, expected):
    source = Location(Path("setup.py"))
    result = list(parse_setup_contents(dedent(file_content), source))
    assert sorted(result) == sorted(expected)


@pytest.mark.parametrize(
    "file_content,expected",
    [
        pytest.param(
            """\
            [options]
            install_requires =
                pandas
                click
            """,
            dependency_factory(["pandas", "click"], "setup.cfg"),
            id="__simple_requirements_in_setup_cfg__succeeds",
        ),
        pytest.param(
            """\
            [metadata]
            license_files = LICENSE
            """,
            [],
            id="__no_requirements_in_setup_cfg__returns_none",
        ),
        pytest.param(
            """\
            [options.extras_require]
            test = pytest
            """,
            [DeclaredDependency("pytest", Location(Path("setup.cfg")))],
            id="__extra_requirements_section_in_setup_cfg__succeeds",
        ),
        pytest.param(
            """\
            [options.tests_require]
            test = pytest
            """,
            [DeclaredDependency("pytest", Location(Path("setup.cfg")))],
            id="__tests_requirements_section_in_setup_cfg__succeeds",
        ),
        pytest.param(
            """\
            [options]
            tests_require =
                hypothesis
                tox
            """,
            dependency_factory(["hypothesis", "tox"], "setup.cfg"),
            id="__tests_requirements_in_setup_cfg__succeeds",
        ),
        pytest.param(
            """\
            [options]
            extras_require =
                hypothesis
                tox
            """,
            dependency_factory(["hypothesis", "tox"], "setup.cfg"),
            id="__extras_requirements_in_setup_cfg__succeeds",
        ),
        pytest.param(
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
            """,
            dependency_factory(
                ["pandas", "click", "tox", "scipy", "pytest", "hypothesis"], "setup.cfg"
            ),
            id="__all_requirements_types_in_setup_cfg__succeeds",
        ),
    ],
)
def test_parse_setup_cfg_contents(file_content, expected):
    source = Location(Path("setup.cfg"))
    result = list(parse_setup_cfg_contents(dedent(file_content), source))
    assert sorted(result) == sorted(expected)


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
    actual = _safe_collect_first_elements_sorted(
        extract_declared_dependencies(project_with_requirements)
    )
    _assert_unordered_equivalence(actual, expect)


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
    actual = _safe_collect_first_elements_sorted(
        extract_declared_dependencies(project_with_setup_and_requirements)
    )
    _assert_unordered_equivalence(actual, expect)


def test_extract_declared_dependencies__parse_only_requirements_from_subdir__returns_list(
    project_with_setup_and_requirements,
):
    "In setup.py requirements are read from dict."
    expect = [
        "pandas",
        "tensorflow",
    ]
    path = project_with_setup_and_requirements / "subdir/requirements.txt"
    actual = _safe_collect_first_elements_sorted(extract_declared_dependencies(path))
    _assert_unordered_equivalence(actual, expect)


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
    actual = _safe_collect_first_elements_sorted(
        extract_declared_dependencies(project_with_setup_pyproject_and_requirements)
    )
    _assert_unordered_equivalence(actual, expect)


def test_extract_declared_dependencies__project_with_pyproject__returns_list(
    project_with_pyproject,
):
    expect = [
        "pandas",
        "pydantic",
        "pylint",
    ]
    actual = _safe_collect_first_elements_sorted(
        extract_declared_dependencies(project_with_pyproject)
    )
    _assert_unordered_equivalence(actual, expect)


def test_extract_declared_dependencies__project_with_setup_cfg__returns_list(
    project_with_setup_cfg,
):
    expect = [
        "pandas",
        "django",
    ]
    actual = _safe_collect_first_elements_sorted(
        extract_declared_dependencies(project_with_setup_cfg)
    )
    _assert_unordered_equivalence(actual, expect)


def test_extract_declared_dependencies__project_with_setup_cfg_pyproject_requirements__returns_list(
    project_with_setup_with_cfg_pyproject_and_requirements,
):
    expect = [
        # from requirements.txt:
        "pandas",
        "click",
        # from setup.py:
        # from setup.cfg:
        "dependencyA",
        "dependencyB",
        # from subdir/dev-requirements.txt:
        "black",
        # from subdir/requirements.txt:
        "pandas",
        "tensorflow",
        # from subdir/requirements-docs.txt:
        "sphinx",
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
    observed = _safe_collect_first_elements_sorted(actual)
    _assert_unordered_equivalence(observed, expect)


def _assert_unordered_equivalence(actual, expected):
    assert sorted(actual) == sorted(expected)


def _safe_collect_first_elements_sorted(pairs):
    return sorted([x for (x, _) in pairs])
