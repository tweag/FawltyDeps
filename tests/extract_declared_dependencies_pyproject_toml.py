"""Test extracting dependencies from pyproject.toml"""
import logging
from pathlib import Path
from textwrap import dedent

import pytest

from fawltydeps.extract_declared_dependencies import parse_pyproject_contents


@pytest.mark.parametrize(
    "pyproject_toml,expected_deps",
    [
        pytest.param(
            dedent(
                """\
                [tool.poetry]

                [tool.poetry.dependencies]
                python = "^3.8"
                isort = "^5.10"
                tomli = "^2.0.1"
                """
            ),
            ["isort", "tomli"],
            id="poetry_main_dependencies",
        ),
        pytest.param(
            dedent(
                """\
                [tool.poetry]

                [tool.poetry.group.dev.dependencies]
                black = "^22"
                mypy = "^0.991"

                [tool.poetry.group.test.dependencies]
                pytest = "^5.0.0"
                """
            ),
            ["black", "mypy", "pytest"],
            id="poetry_group_dependencies",
        ),
        pytest.param(
            dedent(
                """\
                [tool.poetry]

                [tool.poetry.extras]
                test = ["pytest < 5.0.0", "pytest-cov[all]"]
                dev = ["pylint >= 2.15.8"]
                """
            ),
            ["pytest", "pytest-cov", "pylint"],
            id="poetry_extra_dependencies",
        ),
        pytest.param(
            dedent(
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
            ),
            [
                "isort",
                "tomli",
                "black",
                "mypy",
                "django",
                "pytest",
                "pytest-cov",
                "pylint",
            ],
            id="poetry_main_group_and_extra_dependencies",
        ),
        pytest.param(
            dedent(
                """\
                [project]
                name = "fawltydeps"

                dependencies = ["isort", "django>2.1; os_name != 'nt'"]
                """
            ),
            ["isort", "django"],
            id="pep621_main_dependencies",
        ),
        pytest.param(
            dedent(
                """\
                [project]

                [project.optional-dependencies]
                test = ["pytest < 5.0.0", "pytest-cov[all]"]
                dev = ["pylint >= 2.15.8"]
                """
            ),
            ["pytest", "pytest-cov", "pylint"],
            id="pep621_optional_dependencies",
        ),
        pytest.param(
            dedent(
                """\
                [project]
                name = "fawltydeps"

                dependencies = ["isort", "django>2.1; os_name != 'nt'"]

                [project.optional-dependencies]
                test = ["pytest < 5.0.0", "pytest-cov[all]"]
                dev = ["pylint >= 2.15.8"]
                """
            ),
            ["isort", "django", "pytest", "pytest-cov", "pylint"],
            id="pep_621_main_and_optional_dependencies",
        ),
        pytest.param(
            dedent(
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
            ),
            [
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
            ],
            id="pep_621_and_poetry_all_dependencies",
        ),
    ],
)
def test_parse_pyproject_content__pep621_or_poetry_dependencies__yields_dependencies(
    pyproject_toml, expected_deps
):
    filename = Path("pyproject.toml")
    result = list(parse_pyproject_contents(pyproject_toml, filename))
    expected = [(dep, filename) for dep in expected_deps]
    assert result == expected


@pytest.mark.parametrize(
    "pyproject_toml,expected,metadata_standard,field_types",
    [
        pytest.param(
            dedent(
                """\
                [tool.poetry]
                dependencies = ["pylint"]
                """
            ),
            [],
            "Poetry",
            ["main"],
            id="poetry_dependencies_as_list",
        ),
        pytest.param(
            dedent(
                """\
                [tool.poetry]
                dependencies = "pylint"
                """
            ),
            [],
            "Poetry",
            ["main"],
            id="poetry_dependencies_as_str",
        ),
        pytest.param(
            dedent(
                """\
                [tool.poetry]
                [tool.poetry.group.dev]
                dependencies = ["black > 22", "mypy"]
                """
            ),
            [],
            "Poetry",
            ["group"],
            id="poetry_dependencies_as_list",
        ),
        pytest.param(
            dedent(
                """\
                [tool.poetry]
                [tool.poetry.extras]
                test = "pytest"
                """
            ),
            [],
            "Poetry",
            ["extra"],
            id="poetry_extra_requirements_as_str_instead_of_list",
        ),
        pytest.param(
            dedent(
                """\
                [tool.poetry]
                extras = ["pytest"]
                """
            ),
            [],
            "Poetry",
            ["extra"],
            id="poetry_extra_requirements_as_list_instead_of_dict",
        ),
        pytest.param(
            dedent(
                """\
                [tool.poetry]

                dependencies = ["pylint"]

                [tool.poetry.group.dev]
                dependencies = ["black > 22", "mypy"]

                [tool.poetry.extras]
                black = "^22"
                """
            ),
            [],
            "Poetry",
            ["main", "group", "extra"],
            id="poetry_all_dependencies_malformatted",
        ),
        pytest.param(
            dedent(
                """\
                [project.dependencies]
                pylint = ""
                """
            ),
            [],
            "PEP621",
            ["main"],
            id="pep621_dependencies_as_dict_instead_of_list",
        ),
        pytest.param(
            dedent(
                """\
                [project]
                optional-dependencies = ["pylint"]
                """
            ),
            [],
            "PEP621",
            ["optional"],
            id="pep621_optional_dependencies_as_list_instead_of_dict",
        ),
    ],
)
def test_parse_pyproject_content__malformatted_poetry_dependencies__yields_no_dependencies(
    caplog, pyproject_toml, expected, metadata_standard, field_types
):
    path_hint = Path("pyproject.toml")
    result = list(parse_pyproject_contents(pyproject_toml, path_hint))
    assert result == expected
    for field_type in field_types:
        assert (
            f"Failed to parse {metadata_standard} {field_type} dependencies in {path_hint}."
            in caplog.text
        )


@pytest.mark.parametrize(
    "pyproject_toml,expected,expected_logs",
    [
        pytest.param(
            dedent(
                """\
                [project]
                name = "fawltydeps"
                """
            ),
            [],
            [("PEP621", "main"), ("PEP621", "optional")],
            id="missing_pep621_fields",
        ),
        pytest.param(
            dedent(
                """\
                [tool.poetry]
                name = "fawltydeps"
                """
            ),
            [],
            [
                ("PEP621", "main"),
                ("PEP621", "optional"),
                ("Poetry", "main"),
                ("Poetry", "group"),
                ("Poetry", "extra"),
            ],
            id="missing_pep621_and_poetry_fields",
        ),
    ],
)
def test_parse_pyproject_contents__missing_dependencies__logs_debug_message(
    caplog, tmp_path, pyproject_toml, expected, expected_logs
):
    caplog.set_level(logging.DEBUG)
    path_hint = tmp_path / "pyproject.toml"

    result = list(parse_pyproject_contents(pyproject_toml, path_hint))

    assert expected == result

    for metadata_standard, field_type in expected_logs:
        assert (
            f"Failed to find {metadata_standard} {field_type} dependencies in {path_hint}"
            in caplog.text
        )
