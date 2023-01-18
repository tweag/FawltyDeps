"""
Integration tests for the FawltyDeps project

Check for given a simple project that following workflows work:
- discover all imports and dependencies 
  and correctly identify unused and missing dependencies
- given only part of the project to search in
  correctly identify unused and missing dependencies

Sample projects from `tests/project_gallery` are used via fixtures.


"""
from fawltydeps.check import compare_imports_to_dependencies, DependencyComparison
from fawltydeps.extract_imports import parse_any_arg
from fawltydeps.extract_dependencies import extract_dependencies
from pathlib import Path
import pytest
import os
import sys
import shutil
from itertools import groupby

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=E1101
else:
    import tomli as tomllib


@pytest.fixture
def datadir(tmp_path: Path) -> Path:

    test_dir = "./tests/projects_gallery"
    if os.path.isdir(test_dir):
        shutil.copytree(test_dir, tmp_path / "data")

    return tmp_path / "data"


def test_integration_compare_imports_to_dependencies(datadir):

    project_path = datadir / "file__requirements"
    extracted_dependencies = list(extract_dependencies(project_path))
    dependencies = [d.name for d in extracted_dependencies]
    imports = [i.name for i in parse_any_arg(project_path)]

    result = compare_imports_to_dependencies(imports=imports, dependencies=dependencies)
    unused_dependencies_locations = {
        name: [l.location.name for l in locations]
        for name, locations in groupby(extracted_dependencies, key=lambda x: x.name)
        if name in result.unused
    }
    with (project_path / "expected.toml").open("rb") as f:
        expected = tomllib.load(f)

    assert unused_dependencies_locations == expected["unused_deps"]
    assert (result.undeclared or {}) == expected["undeclared_deps"]
