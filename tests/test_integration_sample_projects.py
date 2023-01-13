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
import shutil


@pytest.fixture
def datadir(tmp_path: Path) -> Path:

    test_dir = "./tests/projects_gallery"
    if os.path.isdir(test_dir):
        shutil.copytree(test_dir, tmp_path / "data")

    return tmp_path / "data"


def test_integration_compare_imports_to_dependencies(datadir):

    project_path = datadir / "file__requirements"
    dependencies = [a for a, _ in extract_dependencies(project_path)]
    imports = parse_any_arg(project_path)

    result = compare_imports_to_dependencies(imports=imports, dependencies=dependencies)

    print(result)
    assert result.unused == {"scipy"}
    assert result.undeclared == set()
