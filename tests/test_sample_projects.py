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

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

import pytest

from fawltydeps.main import Analysis
from fawltydeps.settings import Action, Settings, print_toml_config
from fawltydeps.types import TomlData
from tests.utils import SAMPLE_PROJECTS_DIR

from .project_helpers import BaseExperiment, BaseProject, parse_toml

# These are (slow) integration tests that are disabled by default.
pytestmark = pytest.mark.integration


@dataclass
class Experiment(BaseExperiment):
    """A single experiment to run FawltyDeps on a sample project.

    Input to the experiment consists of the following members:
    - code: Settings.code paths relative to the sample project root
    - deps: Settings.deps paths relative to the sample project root
    - pyenvs: Settings.pyenvs paths relative to the sample project root.
              If not given (or None), a cached venv with the requirements from
              BaseExperiment.requirements installed will be used instead.
    - install_deps: Whether or not to include the TemporaryPipInstall resolver
                    when resolving dependencies (default: False)
    - exclude: Settings.exclude strings with gitignore patterns. If not given
               (or None), the default [".*"] pattern is used.

    See BaseExperiment for details on the inherited members.
    """

    code: List[str]
    deps: List[str]
    pyenvs: Optional[List[str]]
    install_deps: bool
    exclude: List[str]
    exclude_from: Optional[List[str]]

    @classmethod
    def from_toml(cls, name: str, data: TomlData) -> Experiment:
        return cls(
            code=data.get("code", [""]),
            deps=data.get("deps", [""]),
            pyenvs=data.get("pyenvs", None),
            install_deps=data.get("install_deps", False),
            exclude=data.get("exclude", None),
            exclude_from=data.get("exclude_from", None),
            **cls._init_args_from_toml(name, data),
        )

    def build_settings(self, cache: pytest.Cache) -> Settings:
        """Construct a Settings object appropriate for this experiment."""
        if self.pyenvs is None:  # use cached venv
            pyenvs = {self.get_venv_dir(cache)}
        else:  # use given pyenvs relative to project directory
            pyenvs = {Path(path) for path in self.pyenvs}
        return Settings(
            actions={Action.REPORT_UNDECLARED, Action.REPORT_UNUSED},
            code={Path(path) for path in self.code},
            deps={Path(path) for path in self.deps},
            pyenvs=pyenvs,
            install_deps=self.install_deps,
            exclude=Settings().exclude if self.exclude is None else set(self.exclude),
            exclude_from={Path(path) for path in (self.exclude_from or [])},
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
    def collect(cls) -> Iterator[SampleProject]:
        for subdir in SAMPLE_PROJECTS_DIR.iterdir():
            toml_path = subdir / "expected.toml"
            if not toml_path.is_file():
                continue
            toml_data = parse_toml(toml_path)
            yield cls(path=subdir, **cls._init_args_from_toml(toml_data, Experiment))


@pytest.mark.parametrize(
    ("project", "experiment"),
    [
        pytest.param(project, experiment, id=experiment.name)
        for project in SampleProject.collect()
        for experiment in project.experiments
    ],
)
def test_sample_projects(request, project, experiment, monkeypatch):
    experiment.maybe_skip(project)
    print(f"Testing sample project: {project.name} under {project.path}")
    print(f"Project description: {project.description}")
    print()
    print(f"Running sample project experiment: {experiment.name}")
    print(f"Experiment description: {experiment.description}")
    print()
    print("Experiment settings:")
    monkeypatch.chdir(project.path)
    settings = experiment.build_settings(request.config.cache)
    print_toml_config(settings)
    print()
    analysis = Analysis.create(settings)
    experiment.expectations.verify_analysis(analysis)
