"""Common helpers shared between test_real_project and test_sample_projects."""
import hashlib
import logging
import shlex
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set, Type

import pytest

from fawltydeps.main import Analysis
from fawltydeps.types import TomlData

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=E1101
else:
    import tomli as tomllib

JsonData = Dict[str, Any]

logger = logging.getLogger(__name__)


@dataclass
class CachedExperimentVenv:
    """A virtualenv used in a sample or real-world experiment.

    This is a test helper to create and reuse virtualenvs that contain real
    packages used in our integration tests. The goal is that venvs are created
    _once_ and reused as long as the commands used to create them and install
    packages into them remain unchanged. These use pytest's caching
    infrastructure meaning that the venvs typically end up living under
    ~/.cache/pytest/d/...
    """

    requirements: List[str]  # PEP 508 requirements, passed to 'pip install'

    def venv_script_lines(self, venv_path: Path) -> List[str]:
        return (
            [
                f"rm -rf {venv_path}",
                f"python3 -m venv {venv_path}",
                f"{venv_path}/bin/pip install --upgrade pip",
            ]
            + [
                f"{venv_path}/bin/pip install {shlex.quote(req)}"
                for req in self.requirements
            ]
            + [
                f"touch {venv_path}/.installed",
            ]
        )

    def venv_hash(self) -> str:
        """Returns a hash that depends on the venv script and python version.

        The installation script will change if the code to setup the venv in
        venv_script_lines() changes, or if the requirements of the experiment
        changes. It will also be different for different Python versions.
        The Python version currently used to run the tests is used to compute
        the hash and create the venv.
        """
        dummy_script = self.venv_script_lines(Path("/dev/null"))
        py_version = f"{sys.version_info.major},{sys.version_info.major}"
        script_and_version_bytes = ("".join(dummy_script) + py_version).encode()
        return hashlib.sha256(script_and_version_bytes).hexdigest()

    def __call__(self, cache: pytest.Cache) -> Path:
        """Get this venv's dir and create it if necessary.

        The venv_dir is where we install the dependencies of the current
        experiment. It is keyed by the sha256 checksum of the requirements
        file and the script we use for setting up the venv. This way, we
        don't risk using a previously cached venv for a different if the
        script or the requirements to create that venv change.
        """
        # We cache venv dirs using the hash from create_venv_hash
        cached_str = cache.get(f"fawltydeps/{self.venv_hash()}", None)
        if cached_str is not None and Path(cached_str, ".installed").is_file():
            return Path(cached_str)  # already cached

        # Must run the script to set up the venv
        venv_dir = Path(cache.mkdir(f"fawltydeps_venv_{self.venv_hash()}"))
        logger.info(f"Creating venv at {venv_dir}...")
        venv_script = self.venv_script_lines(venv_dir)
        subprocess.run(
            " && ".join(venv_script),
            check=True,  # fail if any of the commands fail
            shell=True,  # pass multiple shell commands to the subprocess
        )
        # Make sure the venv has been installed
        assert (venv_dir / ".installed").is_file()
        cache.set(f"fawltydeps/{self.venv_hash()}", str(venv_dir))
        return venv_dir


@dataclass
class AnalysisExpectations:
    """Encode our expectations on the analysis resulting from an experiment.

    Encapsulate the expected values of an Analysis object (or its JSON
    counterpart) after a real/sample project experiment has been run.

    The members of this expectation object are all optional; if omitted, the
    corresponding Analysis member will _not_ be checked. Furthermore, no "deep"
    verification of each member is performed here; rather, we only check that
    the set of (import or dependency) names that can found in each Analysis
    member match the expected set stored here.
    """

    imports: Optional[Set[str]] = None
    declared_deps: Optional[Set[str]] = None
    undeclared_deps: Optional[Set[str]] = None
    unused_deps: Optional[Set[str]] = None

    @classmethod
    def from_toml(cls, data: TomlData) -> "AnalysisExpectations":
        """Read expectations from the given TOML table."""

        def set_or_none(data: Optional[Iterable[str]]) -> Optional[Set[str]]:
            return None if data is None else set(data)

        return cls(
            imports=set_or_none(data.get("imports")),
            declared_deps=set_or_none(data.get("declared_deps")),
            undeclared_deps=set_or_none(data.get("undeclared_deps")),
            unused_deps=set_or_none(data.get("unused_deps")),
        )

    def _verify_members(self, member_extractor: Callable[[str], Set[str]]) -> None:
        for member in dataclass_fields(self):
            expected_names = getattr(self, member.name)
            if expected_names is None:
                print(f"Skip checking .{member.name}")
                continue

            print(f"Checking .{member.name}")
            actual_names = member_extractor(member.name)
            print(f"  Actual names: {sorted(actual_names)}")
            print(f"  Expect names: {sorted(expected_names)}")
            assert actual_names == expected_names

    def verify_analysis(self, analysis: Analysis) -> None:
        """Assert that the given Analysis object matches our expectations."""
        self._verify_members(lambda member: {m.name for m in getattr(analysis, member)})

    def verify_analysis_json(self, analysis: JsonData) -> None:
        """Assert that the given JSON analysis matches our expectations."""
        self._verify_members(lambda member: {m["name"] for m in analysis[member]})


@dataclass
class BaseExperiment(ABC):
    """A single experiment, running FawltyDeps on a test project.

    An experiment is part of a bigger project (see BaseProject below) and has:
    - A name and description, for documentation purposes.
    - A list of requirements, to be installed into a virtualenv and made
      available to FawltyDeps when this experiment is run
      (see CachedExperimentVenv for details).
    - A set of expectations on the resulting Analysis object, to be verified
      after the FawltyDeps has been run (see AnalysisExpectations for details).
    """

    name: str
    description: Optional[str]
    requirements: List[str]
    expectations: AnalysisExpectations

    @staticmethod
    def _init_args_from_toml(name: str, data: TomlData) -> Dict[str, Any]:
        """Extract members from TOML into kwargs for a subclass constructor."""
        return dict(
            name=name,
            description=data.get("description"),
            requirements=data.get("requirements", []),
            expectations=AnalysisExpectations.from_toml(data),
        )

    @classmethod
    @abstractmethod
    def from_toml(cls, name: str, data: TomlData) -> "BaseExperiment":
        """Create an instance from TOML data."""
        raise NotImplementedError

    def get_venv_dir(self, cache: pytest.Cache) -> Path:
        """Get this venv's dir and create it if necessary."""
        return CachedExperimentVenv(self.requirements)(cache)


@dataclass
class BaseProject(ABC):
    """Encapsulate a Python project to be tested with FawltyDeps.

    This represents a project on which we want to run FawltyDeps in one or more
    experiments. It has at least:
    - A name and optional description, for documentation purposes.
    - A list of experiments (see BaseExperiment above), describing one or more
      scenarios for running FawltyDeps on this project, and what results to
      expect in those scenarios.
    """

    name: str
    description: Optional[str]
    experiments: List[BaseExperiment]

    @staticmethod
    def _init_args_from_toml(
        toml_data: TomlData, ExperimentClass: Type[BaseExperiment]
    ) -> Dict[str, Any]:
        """Extract members from TOML into kwargs for a subclass constructor."""
        # We ultimately _trust_ the .toml files read here, so we can skip all
        # the usual error checking associated with validating external data.
        project_name = toml_data["project"]["name"]
        return dict(
            name=project_name,
            description=toml_data["project"].get("description"),
            experiments=[
                ExperimentClass.from_toml(f"{project_name}:{name}", data)
                for name, data in toml_data["experiments"].items()
            ],
        )

    @classmethod
    @abstractmethod
    def collect(cls) -> Iterator["BaseProject"]:
        """Find and generate all projects in this test suite."""
        raise NotImplementedError


def parse_toml(toml_path: Path) -> TomlData:
    try:
        with toml_path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError:
        print(f"Error occurred while parsing file: {toml_path}")
        raise
