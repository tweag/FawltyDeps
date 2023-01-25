"""
Integration tests for the FawltyDeps project

Check for given a simple project that following workflows work:
- discover all imports and dependencies
  and correctly identify unused and missing dependencies
- TODO given only part of the project to search in
  correctly identify unused and missing dependencies

Sample projects from `tests/sample_projects` are auto-dicovered and
used in `sample_projects_params.

The structure of sample project is following
```
└── sample_project
    ├── expected.toml (mandatory)
    └── ... (regular Python project)
```
"""
import sys
from pathlib import Path

import pytest

from fawltydeps.main import Action, Analysis
from fawltydeps.types import FileLocation

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=E1101
else:
    import tomli as tomllib

# These are (slow) integration tests that are disabled by default.
pytestmark = pytest.mark.integration

test_dir = Path("./tests/sample_projects")

sample_projects_params = [
    pytest.param(sample_project, id=sample_project.name)
    for sample_project in test_dir.iterdir()
    if sample_project.is_dir()
]


@pytest.mark.parametrize("project_path", sample_projects_params)
def test_integration_analysis_on_sample_projects__(project_path):

    actions = {Action.REPORT_UNDECLARED, Action.REPORT_UNUSED}
    analysis = Analysis.create(actions, code=project_path, deps=project_path)

    with (project_path / "expected.toml").open("rb") as f:
        expected = tomllib.load(f)

    # parse FileLocation from toml file
    expected["undeclared_deps"] = {
        k: [
            FileLocation(project_path / value["path"], value.get("lineno"))
            for value in v
        ]
        for k, v in expected["undeclared_deps"].items()
    }

    assert analysis.unused_deps == set(expected["unused_deps"].keys())
    assert analysis.undeclared_deps == expected["undeclared_deps"]
