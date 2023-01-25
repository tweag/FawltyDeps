"""
Integration tests for the FawltyDeps project

Check for given a simple project that following workflows work:
- discover all imports and dependencies
  and correctly identify unused and missing dependencies
- given only part of the project to search in
  correctly identify unused and missing dependencies

Sample projects from `tests/project_gallery` are used via fixtures.


"""
import os
import shutil
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


@pytest.fixture
def datadir(tmp_path: Path) -> Path:

    test_dir = "./tests/sample_projects"
    if os.path.isdir(test_dir):
        shutil.copytree(test_dir, tmp_path / "data")

    return tmp_path / "data"


def test_integration_compare_imports_to_dependencies(datadir):

    # project_path = datadir / "file__requirements_unused"
    project_path = datadir / "file__requirements_undeclared"

    actions = {Action.REPORT_UNDECLARED, Action.REPORT_UNUSED}
    analysis = Analysis.create(actions, code=project_path, deps=project_path)

    with (project_path / "expected.toml").open("rb") as f:
        expected = tomllib.load(f)

    # parse FileLocation properly
    expected["undeclared_deps"] = {
        k: [
            FileLocation(project_path / value["path"], value.get("lineno"))
            for value in v
        ]
        for k, v in expected["undeclared_deps"].items()
    }

    assert analysis.unused_deps == set(expected["unused_deps"].keys())
    assert analysis.undeclared_deps == expected["undeclared_deps"]
