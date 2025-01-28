"""Test extracting dependencies from pyproject.toml."""

import logging
from dataclasses import dataclass, field
from typing import List

import pytest

from fawltydeps.extract_deps.pyproject_toml_parser import parse_pyproject_toml
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
        pytest.param(
            """\
            [project]
            name = "my_project"
            requires-python = ">=3.9"
            dependencies = [
                "numpy",
                "pandas",
                "matplotlib",
            ]

            [tool.pixi.project]
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]
            """,
            ["numpy", "pandas", "matplotlib"],
            id="pixi_pyproject_pep621_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            requires-python = ">=3.9"

            [tool.pixi.project]
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [tool.pixi.dependencies]
            numpy = "*"
            pandas = "*"
            matplotlib = "*"
            """,
            ["numpy", "pandas", "matplotlib"],
            id="pixi_pyproject_conda_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            requires-python = ">=3.9"
            dependencies = [
                "numpy",
                "pandas",
                "matplotlib",
            ]

            [tool.pixi.project]
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [tool.pixi.dependencies]
            numpy = "*"
            pandas = "*"
            matplotlib = "*"
            """,
            ["numpy", "pandas", "matplotlib"],
            id="pixi_pyproject_pep621_and_conda_same_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            requires-python = ">=3.9"
            dependencies = [
                "numpy",
                "pandas",
            ]

            [tool.pixi.project]
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [tool.pixi.dependencies]
            pandas = "*"
            matplotlib = "*"
            """,
            ["pandas", "matplotlib", "numpy"],
            id="pixi_pyproject_pep621_and_conda_different_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            requires-python = ">= 3.9"

            [tool.pixi.project]
            channels = ["conda-forge"]
            platforms = ["linux-64"]

            [tool.pixi.pypi-dependencies]
            numpy = "*"
            """,
            ["numpy"],
            id="pixi_pyproject_pypi_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            requires-python = ">= 3.9"

            [tool.pixi.project]
            channels = ["conda-forge"]
            platforms = ["linux-64"]

            [tool.pixi.feature.my_feature.dependencies]
            pandas = "*"
            """,
            ["pandas"],
            id="pixi_pyproject_optional_conda_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            requires-python = ">= 3.9"

            [tool.pixi.project]
            channels = ["conda-forge"]
            platforms = ["linux-64"]

            [tool.pixi.feature.my_feature.pypi-dependencies]
            pandas = "*"
            """,
            ["pandas"],
            id="pixi_pyproject_optional_pypi_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            requires-python = ">= 3.9"
            dependencies = [
                "dep1",
                "twice",
            ]

            [project.optional-dependencies]
            group1 = ["dep2"]

            [tool.pixi.project]
            channels = ["conda-forge"]
            platforms = ["linux-64"]

            [tool.pixi.dependencies]
            dep3 = "*"
            twice = "*"

            [tool.pixi.pypi-dependencies]
            dep4 = "*"

            [tool.pixi.feature.feature1.dependencies]
            dep5 = "*"

            [tool.pixi.feature.feature2.dependencies]
            dep6 = "*"

            [tool.pixi.feature.feature2.pypi-dependencies]
            dep7 = "*"
            """,
            ["dep3", "twice", "dep4", "dep5", "dep6", "dep7", "dep1", "dep2"],
            id="pixi_pyproject_mixed_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            requires-python = ">= 3.9"

            [tool.pixi.project]
            channels = ["conda-forge"]
            platforms = ["linux-64"]

            [tool.pixi.pypi-dependencies]
            my_project = { path = ".", editable = true }
            pandas = "*"
            """,
            ["pandas"],
            id="pixi_pyproject_self_dep_is_ignored",
        ),
        pytest.param(
            """\
            [project]
            name = "myapp"
            version = "1.0"
            description = "My App"
            requires-python = ">=3.13"
            dependencies = [
                "flask",
            ]

            [dependency-groups]
            dev = [
                "debugpy",
                "fawltydeps>=0.18.0",
                "pytest>=8.3.4",
                "pytest-flask",
                "pytest-order",
                "pytest-timeout",
                "rich",
                "ruff",
                "watchdog>=6.0.0",
            ]
            """,
            [
                "flask",
                "debugpy",
                "fawltydeps",
                "pytest",
                "pytest-flask",
                "pytest-order",
                "pytest-timeout",
                "rich",
                "ruff",
                "watchdog",
            ],
            id="pep735_dependency_groups",
        ),
        pytest.param(
            """\
            [dependency-groups]
            test = ["pytest", "coverage"]
            docs = ["sphinx", "sphinx-rtd-theme"]
            typing = ["mypy", "types-requests"]
            typing-test = [{include-group = "typing"}, {include-group = "test"}, "useful-types"]
            """,
            [
                "pytest",
                "coverage",
                "sphinx",
                "sphinx-rtd-theme",
                "mypy",
                "types-requests",
                "useful-types",
            ],
            id="pep735_dependency_groups_with_include_group",
        ),
    ],
)
def test_parse_pyproject_toml__wellformed_dependencies__yields_dependencies(
    write_tmp_files, pyproject_toml, expected_deps
):
    tmp_path = write_tmp_files({"pyproject.toml": pyproject_toml})
    path = tmp_path / "pyproject.toml"

    result = list(parse_pyproject_toml(path))
    expected = [DeclaredDependency(dep, Location(path)) for dep in expected_deps]
    assert result == expected


def test_parse_pyproject_toml__invalid_toml__yields_no_deps_and_error_message(
    write_tmp_files, caplog
):
    tmp_path = write_tmp_files({"pyproject.toml": "[this is not valid toml\n"})
    path = tmp_path / "pyproject.toml"

    caplog.set_level(logging.ERROR)
    result = list(parse_pyproject_toml(path))
    assert result == []
    assert f"Failed to parse {path}:" in caplog.text


@dataclass
class PyprojectTestVector:
    """Test vectors for parsing of malformed pyproject.toml."""

    id: str
    data: str
    metadata_standard: str  # possible values: 'Poetry', 'PEP621', 'Pixi'
    field_types: List[str]
    expect: List[str] = field(default_factory=list)


pyproject_tests_malformed_samples = [
    PyprojectTestVector(
        id="poetry_dependencies_as_one_element_list",
        data="""\
            [tool.poetry]
            dependencies = ["pylint"]
            """,
        metadata_standard="Poetry",
        field_types=["main"],
    ),
    PyprojectTestVector(
        id="poetry_dependencies_as_str",
        data="""\
            [tool.poetry]
            dependencies = "pylint"
            """,
        metadata_standard="Poetry",
        field_types=["main"],
    ),
    PyprojectTestVector(
        id="poetry_dependencies_as_list",
        data="""\
            [tool.poetry]
            [tool.poetry.group.dev]
            dependencies = ["black > 22", "mypy"]
            """,
        metadata_standard="Poetry",
        field_types=["group"],
    ),
    PyprojectTestVector(
        id="poetry_extra_requirements_as_str_instead_of_list",
        data="""\
            [tool.poetry]
            [tool.poetry.extras]
            test = "pytest"
            """,
        metadata_standard="Poetry",
        field_types=["extra"],
    ),
    PyprojectTestVector(
        id="poetry_extra_requirements_as_list_instead_of_dict",
        data="""\
            [tool.poetry]
            extras = ["pytest"]
            """,
        metadata_standard="Poetry",
        field_types=["extra"],
    ),
    PyprojectTestVector(
        id="poetry_all_dependencies_malformed",
        data="""\
            [tool.poetry]

            dependencies = ["pylint"]

            [tool.poetry.group.dev]
            dependencies = ["black > 22", "mypy"]

            [tool.poetry.extras]
            black = "^22"
            """,
        metadata_standard="Poetry",
        field_types=["main", "group", "extra"],
    ),
    PyprojectTestVector(
        id="pep621_dependencies_as_dict_instead_of_list",
        data="""\
            [project.dependencies]
            pylint = ""
            """,
        metadata_standard="PEP621",
        field_types=["main"],
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
    PyprojectTestVector(
        id="pixi_conda_dependencies_as_one_element_list",
        data="""\
            [tool.pixi]
            dependencies = ["pylint"]
            """,
        metadata_standard="Pixi",
        field_types=["main"],
    ),
    PyprojectTestVector(
        id="pixi_conda_dependencies_as_str",
        data="""\
            [tool.pixi]
            dependencies = "pylint"
            """,
        metadata_standard="Pixi",
        field_types=["main"],
    ),
    PyprojectTestVector(
        id="pixi_pypi_dependencies_as_one_element_list",
        data="""\
            [tool.pixi]
            pypi-dependencies = ["pylint"]
            """,
        metadata_standard="Pixi",
        field_types=["pypi"],
    ),
    PyprojectTestVector(
        id="pixi_pypi_dependencies_as_str",
        data="""\
            [tool.pixi]
            pypi-dependencies = "pylint"
            """,
        metadata_standard="Pixi",
        field_types=["pypi"],
    ),
    PyprojectTestVector(
        id="pixi_feature_conda_dependencies_as_list",
        data="""\
            [tool.pixi]
            [tool.pixi.feature.dev]
            dependencies = ["black > 22", "mypy"]
            """,
        metadata_standard="Pixi",
        field_types=["feature"],
    ),
    PyprojectTestVector(
        id="pixi_feature_conda_dependencies_as_str",
        data="""\
            [tool.pixi]
            [tool.pixi.feature.dev]
            dependencies = "pytest"
            """,
        metadata_standard="Pixi",
        field_types=["feature"],
    ),
    PyprojectTestVector(
        id="pixi_feature_pypi_dependencies_as_list",
        data="""\
            [tool.pixi]
            [tool.pixi.feature.dev]
            pypi-dependencies = ["black > 22", "mypy"]
            """,
        metadata_standard="Pixi",
        field_types=["feature pypi"],
    ),
    PyprojectTestVector(
        id="pixi_feature_pypi_dependencies_as_str",
        data="""\
            [tool.pixi]
            [tool.pixi.feature.dev]
            pypi-dependencies = "pytest"
            """,
        metadata_standard="Pixi",
        field_types=["feature pypi"],
    ),
    PyprojectTestVector(
        id="pixi_all_dependencies_malformed",
        data="""\
            [tool.pixi]
            dependencies = ["pylint"]
            pypi-dependencies = "pytest"

            [tool.pixi.feature.dev]
            dependencies = ["black > 22", "mypy"]
            pypi-dependencies = "numpy"
            """,
        metadata_standard="Pixi",
        field_types=["main", "pypi", "feature", "feature pypi"],
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in pyproject_tests_malformed_samples]
)
def test_parse_pyproject_content__malformed_deps__yields_no_deps(
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
        pytest.param(
            """\
            [tool.pixi.dependencies]
            numpy = "*"

            [tool.pixi.feature.dev.pypi-dependencies]
            pandas = "*"
            """,
            ["numpy", "pandas"],
            [
                ("Pixi", "pypi"),
                ("PEP621", "main"),
                ("PEP621", "optional"),
            ],
            id="missing_pixi_and_pep621_fields",
        ),
        pytest.param(
            """\
            [tool.pixi]
            """,
            [],
            [
                ("Pixi", "main"),
                ("Pixi", "pypi"),
                ("Pixi", "feature"),
                ("Pixi", "feature pypi"),
                ("PEP621", "main"),
                ("PEP621", "optional"),
            ],
            id="missing_pixi_fields",
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
    expected_deps = [DeclaredDependency(dep, Location(path)) for dep in expected]
    assert expected_deps == result
    for metadata_standard, field_type in expected_logs:
        assert (
            f"Failed to find {metadata_standard} {field_type} dependencies in {path}"
            in caplog.text
        )
