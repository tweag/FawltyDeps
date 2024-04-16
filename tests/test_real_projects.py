"""Verify behavior of FawltyDeps on real Python projects.

These are bigger integration tests that are not meant to be run on every commit.
We download/extract pinned releases several 3rd-party Python projects, and run
FawltyDeps on them, with hardcoded expectations per project on what FawltyDeps
should find/report.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

import pytest
from pkg_resources import Requirement

from fawltydeps.packages import LocalPackageResolver, pyenv_sources
from fawltydeps.types import TomlData

from .project_helpers import (
    BaseExperiment,
    BaseProject,
    JsonData,
    TarballPackage,
    parse_toml,
)

logger = logging.getLogger(__name__)

# Each of these tests will download and unpack a 3rd-party project before analyzing it;
# therefore, they're slow and are skipped by default.
pytestmark = pytest.mark.integration

# Directory with .toml files that define test cases for selected tarballs from
# 3rd-party/real-world projects.
REAL_PROJECTS_DIR = Path(__file__).with_name("real_projects")


def verify_requirements(venv_path: Path, requirements: List[str]) -> None:
    deps = {
        Requirement.parse(req).unsafe_name
        for req in requirements
        if "python_version" not in req  # we don't know how to parse these (yet)
    }
    resolved = LocalPackageResolver(pyenv_sources(venv_path)).lookup_packages(deps)
    assert all(dep in resolved for dep in deps)


def run_fawltydeps_json(
    *args: str, venv_dir: Optional[Path], cwd: Optional[Path] = None
) -> JsonData:
    argv = [sys.executable, "-I", "-m", "fawltydeps", "--json"]
    if venv_dir is not None:
        argv += [f"--pyenv={venv_dir}", "--pyenv=."]
    argv += [arg.replace("$REAL_PROJECTS_DIR", str(REAL_PROJECTS_DIR)) for arg in args]
    proc = subprocess.run(argv, stdout=subprocess.PIPE, check=False, cwd=cwd)
    # Check if return code does not indicate error (see main.main for the full list)
    assert proc.returncode in {0, 3, 4}
    return json.loads(proc.stdout)  # type: ignore[no-any-return]


@dataclass
class Experiment(BaseExperiment):
    """A single experiment to run FawltyDeps on a real world project.

    The given 'args' are passed as command line arguments to `fawltydeps`.
    See BaseExperiment for details on the inherited members.
    """

    args: List[str]

    @classmethod
    def from_toml(cls, name: str, data: TomlData) -> Experiment:
        return cls(args=data["args"], **cls._init_args_from_toml(name, data))


@dataclass
class ThirdPartyProject(BaseProject):
    """Encapsulate a 3rd-party project to be tested with FawltyDeps.

    This ultimately identifies a tarball containing a 3rd-party Python project,
    and the things we expect FawltyDeps to find when run on that unpacked
    tarball.

    The actual data populating these objects is read from TOML files in
    REAL_PROJECTS_DIR, and the tarballs are downloaded, unpacked, and cached
    by the methods below.
    """

    toml_path: Path
    tarball: TarballPackage

    @classmethod
    def collect(cls) -> Iterator[ThirdPartyProject]:
        for path in filter(lambda p: p.suffix == ".toml", REAL_PROJECTS_DIR.iterdir()):
            toml_data = parse_toml(path)
            project_info = cls._init_args_from_toml(toml_data, Experiment)
            yield cls(
                toml_path=path,
                tarball=TarballPackage(
                    filename_must_include=project_info["name"],
                    url=toml_data["project"]["url"],
                    sha256=toml_data["project"]["sha256"],
                ),
                **project_info,
            )

    def get_unpack_dir(self, tarball_path: Path, cache: pytest.Cache) -> Path:
        """Get this project's unpack dir. Unpack the given tarball if necessary.

        The unpack dir is where we unpack the project's tarball. It is keyed by
        the sha256 checksum of the tarball, so that we don't risk reusing a
        previously cached unpack dir for a different tarball.
        """
        # We cache unpacked tarballs using the given sha256 sum
        cached_str = cache.get(self.unpacked_project_key, None)
        if cached_str is not None and Path(cached_str).is_dir():
            return Path(cached_str)  # already cached

        # Must unpack
        unpack_dir = self.unpacked_project_dir(cache)
        logger.info(f"Unpacking {tarball_path} to {unpack_dir}...")
        with tarfile.open(tarball_path) as f:
            f.extractall(unpack_dir)  # noqa: S202
        assert unpack_dir.is_dir()
        cache.set(self.unpacked_project_key, str(unpack_dir))
        return unpack_dir

    def get_project_dir(self, cache: pytest.Cache) -> Path:
        """Return the cached/unpacked project directory for this project.

        This makes use of the caching mechanism in pytest, documented on
        https://docs.pytest.org/en/7.1.x/reference/reference.html#config-cache.
        The caching happens in two stages: we cache the downloaded tarball,
        as well as the project directory that results from unpacking it.

        The unpacked tarball is keyed by the given sha256. Thus an updated
        sha256 will cause (a new download and) a new unpack.

        The actual integrity check only happens immediately after a download,
        hence we assume that the local cache (both the downloaded tarball, as
        well as the unpacked tarball) is uncorrupted and immutable.
        """
        tarball_path = self.tarball.get(cache)
        logger.info(f"Cached tarball is at: {tarball_path}")
        unpack_dir = self.get_unpack_dir(tarball_path, cache)

        # Most tarballs contains a single leading directory; descend into it.
        entries = list(unpack_dir.iterdir())
        project_dir = entries[0] if len(entries) == 1 else unpack_dir

        logger.info(f"Unpacked project is at {project_dir}")
        return project_dir

    @property
    def unpacked_project_key(self) -> str:
        return f"fawltydeps/{self.tarball.sha256}"

    def unpacked_project_dir(self, cache: pytest.Cache) -> Path:
        return Path(cache.mkdir(f"fawltydeps_{self.tarball.sha256}"))


@pytest.mark.parametrize(
    ("project", "experiment"),
    [
        pytest.param(project, experiment, id=experiment.name)
        for project in ThirdPartyProject.collect()
        for experiment in project.experiments
    ],
)
def test_real_project(request, project, experiment):
    experiment.maybe_skip(project)
    project_dir = project.get_project_dir(request.config.cache)
    venv_dir = experiment.get_venv_dir(request.config.cache)

    print(f"Testing real project {project.name!r} under {project_dir}")
    print(f"Project description: {project.description}")
    print(f"Virtual environment under {venv_dir}")
    print()
    print(f"Running real project experiment: {experiment.name}")
    print(f"Experiment description: {experiment.description}")
    print()

    verify_requirements(venv_dir, experiment.requirements)
    analysis = run_fawltydeps_json(
        *experiment.args,
        venv_dir=venv_dir,
        cwd=project_dir,
    )

    experiment.expectations.verify_analysis_json(analysis)
