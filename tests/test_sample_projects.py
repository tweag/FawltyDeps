"""Verify behavior of FawltyDeps on sample projects.

Check for a given simple project that the following workflows work:
- discover all imports and dependencies
  and correctly identify unused and missing dependencies
- given only part of the project to search in
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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List

import pytest

from fawltydeps.main import Analysis
from fawltydeps.settings import Action, Settings
from fawltydeps.types import TomlData

from .project_helpers import BaseExperiment, BaseProject

# These are (slow) integration tests that are disabled by default.
pytestmark = pytest.mark.integration

SAMPLE_PROJECTS_DIR = Path(__file__).with_name("sample_projects")


@dataclass
class Experiment(BaseExperiment):
    """A single experiment to run FawltyDeps on a sample project.

    Input to the experiment consists of the following members:
    - code: Settings.code paths relative to the sample project root
    - deps: Settings.deps paths relative to the sample project root

    See BaseExperiment for details on the inherited members.
    """

    code: List[str]
    deps: List[str]

    @classmethod
    def parse_from_toml(cls, name: str, data: TomlData) -> "Experiment":
        return cls(
            code=data.get("code", [""]),
            deps=data.get("deps", [""]),
            **cls.init_args_from_toml(name, data),
        )

    def build_settings(self, project_path: Path, cache: pytest.Cache) -> Settings:
        """Construct a Settings object appropriate for this experiment."""
        return Settings(
            actions={Action.REPORT_UNDECLARED, Action.REPORT_UNUSED},
            code=[(project_path / path) for path in self.code],
            deps=[(project_path / path) for path in self.deps],
            pyenv=self.get_venv_dir(cache),
        )


@dataclass
class SampleProject(BaseProject):
    """Encapsulate a sample project to be tested with FawltyDeps.

    This represents a sample Python project living in a subdirectory under
    tests/sample_projects/, and the things we expect FawltyDeps to find when
    run on this project.

    The actual data populating these objects is read from TOML files under
    SAMPLE_PROJECTS_DIR.
    """

    path: Path  # Directory containing expected.toml, and rest of sample project

    @classmethod
    def collect(cls) -> Iterator["SampleProject"]:
        for subdir in SAMPLE_PROJECTS_DIR.iterdir():
            toml_path = subdir / "expected.toml"
            if not toml_path.is_file():
                continue
            init_args, _ = cls.parse_toml(toml_path, Experiment)
            yield cls(path=subdir, **init_args)


@pytest.mark.parametrize(
    "project, experiment",
    [
        pytest.param(project, experiment, id=experiment.name)
        for project in SampleProject.collect()
        for experiment in project.experiments
    ],
)
def test_integration_analysis_on_sample_projects__(request, project, experiment):
    print(f"Testing sample project: {project.name} under {project.path}")
    print(f"Project description: {project.description}")
    print()
    print(f"Running sample project experiment: {experiment.name}")
    print(f"Experiment description: {experiment.description}")
    print()
    settings = experiment.build_settings(project.path, request.config.cache)
    analysis = Analysis.create(settings)
    experiment.expectations.verify_analysis(analysis)
