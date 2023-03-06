"""
Integration tests for the FawltyDeps project

Check for given a simple project that following workflows work:
- discover all imports and dependencies
  and correctly identify unused and missing dependencies
- TODO given only part of the project to search in
  correctly identify unused and missing dependencies

Sample projects are subdirectories of `tests/sample_projects`. These are
auto-discovered and used in `sample_projects_params` below.

The structure of sample project is as follows:

tests/sample_projects
├── sample_project1
│   ├── expected.toml (mandatory)
│   └── ... (regular Python project)
└── sample_project2
    ├── expected.toml (mandatory)
    └── ... (regular Python project)
"""
import sys
from pathlib import Path

import pytest

from fawltydeps.main import Analysis
from fawltydeps.settings import Action, Settings

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=E1101
else:
    import tomli as tomllib

# These are (slow) integration tests that are disabled by default.
pytestmark = pytest.mark.integration

SAMPLE_PROJECTS_DIR = Path(__file__).with_name("sample_projects")

sample_projects_params = [
    pytest.param(sample_project, id=sample_project.name)
    for sample_project in SAMPLE_PROJECTS_DIR.iterdir()
    if sample_project.is_dir()
]


@pytest.mark.parametrize("project_path", sample_projects_params)
def test_integration_analysis_on_sample_projects__(project_path):
    settings = Settings(
        actions={Action.REPORT_UNDECLARED, Action.REPORT_UNUSED},
        code=project_path,
        deps=project_path,
    )
    analysis = Analysis.create(settings)

    with (project_path / "expected.toml").open("rb") as f:
        experiment = tomllib.load(f)

    print(experiment["project"].get("name"))
    print(experiment["project"].get("description"))
    expected = experiment.get("analysis_result", {})

    if "imports" in expected:
        print("Verifying 'imports'...")
        actual_imports = {i.name for i in analysis.imports}
        expect_imports = set(expected["imports"])
        assert actual_imports == expect_imports

    if "declared_deps" in expected:
        print("Verifying 'declared_deps'...")
        actual_declared = {d.name for d in analysis.declared_deps}
        expect_declared = set(expected["declared_deps"])
        assert actual_declared == expect_declared

    print("Verifying 'undeclared_deps'...")
    actual_undeclared = {u.name for u in analysis.undeclared_deps}
    expect_undeclared = set(expected.get("undeclared_deps", []))
    assert actual_undeclared == expect_undeclared

    print("Verifying 'unused_deps'...")
    actual_unused = {u.name for u in analysis.unused_deps}
    expect_unused = set(expected.get("unused_deps", []))
    assert actual_unused == expect_unused
