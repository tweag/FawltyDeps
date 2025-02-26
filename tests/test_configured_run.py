"""Test configuration-based run of FawltyDeps (i.e. without command-line args).

Run FawltyDeps in a subprocess, using only pyproject.toml to determine its
settings. Specify imports and declared dependencies that occur in the relevant
project, and verify that we get the expected exit code.
"""

from dataclasses import dataclass, field
from textwrap import dedent

import pytest

from .utils import run_fawltydeps_subprocess

pytestmark = pytest.mark.integration


@dataclass
class ConfiguredRunTestVector:
    """Test vectors for FawltyDeps Settings configuration."""

    id: str
    toml_contents: str = ""
    imports: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    expect: int = 0  # exit code


configured_run_tests_samples = [
    ConfiguredRunTestVector(id="empty_pyproject_toml__no_problem_detected"),
    ConfiguredRunTestVector(
        id="with_ignored__no_problem_detected",
        toml_contents="""
            [tool.fawltydeps]
            ignore_undeclared=["foo"]
            ignore_unused=["bar"]
        """,
        imports=["foo"],
        dependencies=["bar"],
    ),
    ConfiguredRunTestVector(
        id="with_ignored_unused__undeclared_detected",
        toml_contents="""
            [tool.fawltydeps]
            ignore_unused=["bar"]
        """,
        imports=["foo"],
        dependencies=["bar"],
        expect=3,
    ),
    ConfiguredRunTestVector(
        id="with_custom_mapping__no_problem_detected",
        toml_contents="""
            [tool.fawltydeps.custom_mapping]
            bar=["foo"]
        """,
        imports=["foo"],
        dependencies=["bar"],
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in configured_run_tests_samples]
)
def test_run_with_pyproject_toml_settings(vector, fake_project):
    tmp_path = fake_project(
        imports=vector.imports,
        declared_deps=vector.dependencies,
    )
    path = tmp_path / "pyproject.toml"
    path.write_text(dedent(vector.toml_contents))

    _, _, exit_code = run_fawltydeps_subprocess(config_file=str(path), cwd=tmp_path)
    assert exit_code == vector.expect
