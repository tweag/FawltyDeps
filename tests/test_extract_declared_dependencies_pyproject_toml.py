"""Test extracting dependencies from pyproject.toml."""

import logging
from dataclasses import dataclass, field
from typing import List

import pytest

from fawltydeps.extract_declared_dependencies import parse_pyproject_toml
from fawltydeps.types import DeclaredDependency, Location


@pytest.mark.parametrize(
    ("pyproject_toml", "expected_deps"),
    [
        pytest.param(
            """\
            [tool.poetry]

            [tool.poetry.dependencies]
            python = "^3.8"
            isort = "^5.10"
            tomli = "^2.0.1"
            """,
            ["isort", "tomli"],
            id="poetry_main_dependencies",
        ),
        pytest.param(
            """\
            [tool.poetry]

            [tool.poetry.group.dev.dependencies]
            black = "^22"
            mypy = "^0.991"

            [tool.poetry.group.test.dependencies]
            pytest = "^5.0.0"
            """,
            ["black", "mypy", "pytest"],
            id="poetry_group_dependencies",
        ),
        pytest.param(
            """\
            [tool.poetry]

            [tool.poetry.extras]
            test = ["pytest < 5.0.0", "pytest-cov[all]"]
            dev = ["pylint >= 2.15.8"]
            """,
            ["pytest", "pytest-cov", "pylint"],
            id="poetry_extra_dependencies",
        ),
        pytest.param(
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
            """,
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
            """\
            [project]
            name = "fawltydeps"

            dependencies = ["isort", "django>2.1; os_name != 'nt'"]
            """,
            ["isort", "django"],
            id="pep621_main_dependencies",
        ),
        pytest.param(
            """\
            [project]

            [project.optional-dependencies]
            test = ["pytest < 5.0.0", "pytest-cov[all]"]
            dev = ["pylint >= 2.15.8"]
            """,
            ["pytest", "pytest-cov", "pylint"],
            id="pep621_optional_dependencies",
        ),
        pytest.param(
            """\
            [project]
            name = "fawltydeps"

            dependencies = ["isort", "django>2.1; os_name != 'nt'"]

            [project.optional-dependencies]
            test = ["pytest < 5.0.0", "pytest-cov[all]"]
            dev = ["pylint >= 2.15.8"]
            """,
            ["isort", "django", "pytest", "pytest-cov", "pylint"],
            id="pep_621_main_and_optional_dependencies",
        ),
        pytest.param(
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
            """,
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
def test_parse_pyproject_toml__pep621_or_poetry_dependencies__yields_dependencies(
    write_tmp_files, pyproject_toml, expected_deps
):
    tmp_path = write_tmp_files({"pyproject.toml": pyproject_toml})
    path = tmp_path / "pyproject.toml"

    result = list(parse_pyproject_toml(path))
    expected = [DeclaredDependency(dep, Location(path)) for dep in expected_deps]
    assert result == expected


@dataclass
class PyprojectTestVector:
    """Test vectors for FawltyDeps Settings configuration."""

    id: str
    data: str
    metadata_standard: str = field(
        default_factory=lambda: "Poetry"
    )  # possible options: 'Poetry' and 'PEP621'; Python 3.7 does not support 'Literal'
    field_types: List[str] = field(default_factory=lambda: ["main"])
    expect: List[str] = field(default_factory=list)


pyproject_tests_malformed_samples = [
    PyprojectTestVector(
        id="poetry_dependencies_as_one_element_list",
        data="""\
            [tool.poetry]
            dependencies = ["pylint"]
            """,
    ),
    PyprojectTestVector(
        id="poetry_dependencies_as_str",
        data="""\
            [tool.poetry]
            dependencies = "pylint"
            """,
    ),
    PyprojectTestVector(
        id="poetry_dependencies_as_list",
        data="""\
            [tool.poetry]
            [tool.poetry.group.dev]
            dependencies = ["black > 22", "mypy"]
            """,
        field_types=["group"],
    ),
    PyprojectTestVector(
        id="poetry_extra_requirements_as_str_instead_of_list",
        data="""\
            [tool.poetry]
            [tool.poetry.extras]
            test = "pytest"
            """,
        field_types=["extra"],
    ),
    PyprojectTestVector(
        id="poetry_extra_requirements_as_list_instead_of_dict",
        data="""\
            [tool.poetry]
            extras = ["pytest"]
            """,
        field_types=["extra"],
    ),
    PyprojectTestVector(
        id="poetry_all_dependencies_malformatted",
        data="""\
            [tool.poetry]

            dependencies = ["pylint"]

            [tool.poetry.group.dev]
            dependencies = ["black > 22", "mypy"]

            [tool.poetry.extras]
            black = "^22"
            """,
        field_types=["main", "group", "extra"],
    ),
    PyprojectTestVector(
        id="pep621_dependencies_as_dict_instead_of_list",
        data="""\
            [project.dependencies]
            pylint = ""
            """,
        metadata_standard="PEP621",
    ),
    PyprojectTestVector(
        id="pep621_optional_dependencies_as_list_instead_of_dict",
        data="""\
            [project]
            optional-dependencies = ["pylint"]
            """,
        metadata_standard="PEP621",
        field_types=["optional"],
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in pyproject_tests_malformed_samples]
)
def test_parse_pyproject_content__malformatted_poetry_dependencies__yields_no_dependencies(
    write_tmp_files, caplog, vector
):
    tmp_path = write_tmp_files({"pyproject.toml": vector.data})
    path = tmp_path / "pyproject.toml"

    caplog.set_level(logging.ERROR)
    result = list(parse_pyproject_toml(path))
    assert result == vector.expect
    for field_type in vector.field_types:
        assert (
            f"Failed to parse {vector.metadata_standard} {field_type} dependencies in {path}"
            in caplog.text
        )


@pytest.mark.parametrize(
    ("pyproject_toml", "expected", "expected_logs"),
    [
        pytest.param(
            """\
            [project]
            name = "fawltydeps"
            """,
            [],
            [("PEP621", "main"), ("PEP621", "optional")],
            id="missing_pep621_fields",
        ),
        pytest.param(
            """\
            [tool.poetry]
            name = "fawltydeps"
            """,
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
def test_parse_pyproject_toml__missing_dependencies__logs_debug_message(
    write_tmp_files, caplog, tmp_path, pyproject_toml, expected, expected_logs
):
    tmp_path = write_tmp_files({"pyproject.toml": pyproject_toml})
    path = tmp_path / "pyproject.toml"

    caplog.set_level(logging.DEBUG)
    result = list(parse_pyproject_toml(path))
    assert expected == result
    for metadata_standard, field_type in expected_logs:
        assert (
            f"Failed to find {metadata_standard} {field_type} dependencies in {path}"
            in caplog.text
        )
