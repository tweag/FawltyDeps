"""Test extracting dependencies from pixi.toml."""

import logging
from dataclasses import dataclass, field
from typing import List

import pytest

from fawltydeps.extract_deps.pixi_toml_parser import parse_pixi_toml
from fawltydeps.types import DeclaredDependency, Location


@pytest.mark.parametrize(
    ("pixi_toml", "expected_deps"),
    [
        pytest.param(
            """\
            [project]
            name = "my_project"
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [dependencies]
            numpy = "*"
            pandas = "*"
            matplotlib = "*"
            """,
            ["numpy", "pandas", "matplotlib"],
            id="pixi_toml_conda_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [pypi-dependencies]
            numpy = "*"
            """,
            ["numpy"],
            id="pixi_toml_pypi_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [dependencies]
            numpy = "*"
            pandas = "*"
            matplotlib = "*"

            [pypi-dependencies]
            numpy = "*"
            pandas = "*"
            matplotlib = "*"
            """,
            ["numpy", "pandas", "matplotlib"],
            id="pixi_toml_conda_and_pypi_same_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [dependencies]
            numpy = "*"
            pandas = "*"

            [pypi-dependencies]
            pandas = "*"
            matplotlib = "*"
            """,
            ["numpy", "pandas", "matplotlib"],
            id="pixi_toml_conda_and_pypi_different_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [feature.my_feature.dependencies]
            pandas = "*"
            """,
            ["pandas"],
            id="pixi_toml_optional_conda_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [feature.my_feature.pypi-dependencies]
            pandas = "*"
            """,
            ["pandas"],
            id="pixi_toml_optional_pypi_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [dependencies]
            dep1 = "*"
            twice = "*"

            [pypi-dependencies]
            dep2 = "*"
            twice = "*"

            [feature.feature1.dependencies]
            dep3 = "*"

            [feature.feature2.dependencies]
            dep4 = "*"

            [feature.feature2.pypi-dependencies]
            dep5 = "*"
            """,
            ["dep1", "twice", "dep2", "dep3", "dep4", "dep5"],
            id="pixi_toml_mixed_deps",
        ),
        pytest.param(
            """\
            [project]
            name = "my_project"
            channels = ["conda-forge"]
            platforms = ["linux-64", "osx-arm64", "osx-64", "win-64"]

            [pypi-dependencies]
            my_project = { path = ".", editable = true }
            pandas = "*"
            """,
            ["pandas"],
            id="pixi_toml_self_dep_is_ignored",
        ),
    ],
)
def test_parse_pixi_toml__wellformed_dependencies__yields_dependencies(
    write_tmp_files, pixi_toml, expected_deps
):
    tmp_path = write_tmp_files({"pixi.toml": pixi_toml})
    path = tmp_path / "pixi.toml"

    result = list(parse_pixi_toml(path))
    expected = [DeclaredDependency(dep, Location(path)) for dep in expected_deps]
    assert result == expected


def test_parse_pixi_toml__invalid_toml__yields_no_deps_and_error_message(
    write_tmp_files, caplog
):
    tmp_path = write_tmp_files({"pixi.toml": "[this is not valid toml\n"})
    path = tmp_path / "pixi.toml"

    caplog.set_level(logging.ERROR)
    result = list(parse_pixi_toml(path))
    assert result == []
    assert f"Failed to parse {path}:" in caplog.text


@dataclass
class PixiTestVector:
    """Test vectors for parsing of malformed pixi.toml."""

    id: str
    data: str
    field_types: List[str]
    expect: List[str] = field(default_factory=list)


pixi_tests_malformed_samples = [
    PixiTestVector(
        id="conda_deps_as_one_element_list",
        data="""\
            dependencies = ["pylint"]
            """,
        field_types=["main"],
    ),
    PixiTestVector(
        id="conda_deps_as_str",
        data="""\
            dependencies = "pylint"
            """,
        field_types=["main"],
    ),
    PixiTestVector(
        id="pypi_deps_as_one_element_list",
        data="""\
            pypi-dependencies = ["pylint"]
            """,
        field_types=["pypi"],
    ),
    PixiTestVector(
        id="pypi_deps_as_str",
        data="""\
            pypi-dependencies = "pylint"
            """,
        field_types=["pypi"],
    ),
    PixiTestVector(
        id="feature_conda_deps_as_list",
        data="""\
            [feature.dev]
            dependencies = ["black > 22", "mypy"]
            """,
        field_types=["feature"],
    ),
    PixiTestVector(
        id="feature_conda_deps_as_str",
        data="""\
            [feature.dev]
            dependencies = "pytest"
            """,
        field_types=["feature"],
    ),
    PixiTestVector(
        id="feature_pypi_deps_as_list",
        data="""\
            [feature.dev]
            pypi-dependencies = ["black > 22", "mypy"]
            """,
        field_types=["feature pypi"],
    ),
    PixiTestVector(
        id="feature_pypi_deps_as_str",
        data="""\
            [feature.dev]
            pypi-dependencies = "pytest"
            """,
        field_types=["feature pypi"],
    ),
    PixiTestVector(
        id="all_deps_malformed",
        data="""\
            dependencies = ["pylint"]
            pypi-dependencies = "pytest"

            [feature.dev]
            dependencies = ["black > 22", "mypy"]
            pypi-dependencies = "numpy"
            """,
        field_types=["main", "pypi", "feature", "feature pypi"],
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in pixi_tests_malformed_samples]
)
def test_parse_pixi_toml__malformed_deps__yields_no_deps(
    write_tmp_files, caplog, vector
):
    tmp_path = write_tmp_files({"pixi.toml": vector.data})
    path = tmp_path / "pixi.toml"

    caplog.set_level(logging.ERROR)
    result = list(parse_pixi_toml(path))
    assert result == vector.expect
    for field_type in vector.field_types:
        assert (
            f"Failed to parse Pixi {field_type} dependencies in {path}" in caplog.text
        )


@pytest.mark.parametrize(
    ("pixi_toml", "expected", "expected_field_types"),
    [
        pytest.param(
            """\
            [project]
            name = "fawltydeps"
            """,
            [],
            {"main", "pypi", "feature", "feature pypi"},
            id="missing_deps_fields",
        ),
        pytest.param(
            """\
            [dependencies]
            numpy = "*"

            [feature.dev.pypi-dependencies]
            pandas = "*"
            """,
            ["numpy", "pandas"],
            {"pypi"},
            id="missing_pypi_deps_fields",
        ),
        pytest.param(
            """\
            [feature.dev.dependencies]
            numpy = "*"

            [feature.dev.pypi-dependencies]
            pandas = "*"
            """,
            ["numpy", "pandas"],
            {"main", "pypi"},
            id="missing_mandatory_deps_fields",
        ),
    ],
)
def test_parse_pixi_toml__missing_dependencies__logs_debug_message(
    write_tmp_files, caplog, tmp_path, pixi_toml, expected, expected_field_types
):
    tmp_path = write_tmp_files({"pixi.toml": pixi_toml})
    path = tmp_path / "pixi.toml"

    caplog.set_level(logging.DEBUG)
    result = list(parse_pixi_toml(path))
    expected_deps = [DeclaredDependency(dep, Location(path)) for dep in expected]
    assert expected_deps == result
    for field_type in expected_field_types:
        assert f"Failed to find Pixi {field_type} dependencies in {path}" in caplog.text
