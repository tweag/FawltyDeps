"""Verify behavior of FawltyDeps on real Python projects.

These are bigger integration tests that are not meant to be run on every commit.
We download/extract pinned releases several 3rd-party Python projects, and run
FawltyDeps on them, with hardcoded expectations per project on what FawltyDeps
should find/report.
"""
import json
import logging
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional
from urllib.parse import urlparse
from urllib.request import urlretrieve

import pytest
from pkg_resources import Requirement

from fawltydeps.packages import LocalPackageResolver
from fawltydeps.types import TomlData

from .project_helpers import (
    BaseExperiment,
    BaseProject,
    JsonData,
    parse_toml,
    sha256sum,
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
    resolved = LocalPackageResolver(venv_path).lookup_packages(deps)
    assert all(dep in resolved for dep in deps)


def run_fawltydeps_json(
    *args: str, venv_dir: Optional[Path], cwd: Optional[Path] = None
) -> JsonData:
    argv = ["fawltydeps", "--config-file=/dev/null", "--json"]
    if venv_dir is not None:
        argv += [f"--pyenv={venv_dir}"]
    proc = subprocess.run(
        argv + list(args),
        stdout=subprocess.PIPE,
        check=False,
        cwd=cwd,
    )
    # Check if return code does not indicate error (see main.main for the full list)
    assert proc.returncode in {0, 3, 4}
    return json.loads(proc.stdout)  # type: ignore


@dataclass
class Experiment(BaseExperiment):
    """A single experiment to run FawltyDeps on a real world project.

    The given 'args' are passed as command line arguments to `fawltydeps`.
    See BaseExperiment for details on the inherited members.
    """

    args: List[str]

    @classmethod
    def from_toml(cls, name: str, data: TomlData) -> "Experiment":
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
    url: str
    sha256: str

    @classmethod
    def collect(cls) -> Iterator["ThirdPartyProject"]:
        for path in filter(lambda p: p.suffix == ".toml", REAL_PROJECTS_DIR.iterdir()):
            toml_data = parse_toml(path)
            yield cls(
                toml_path=path,
                url=toml_data["project"]["url"],
                sha256=toml_data["project"]["sha256"],
                **cls._init_args_from_toml(toml_data, Experiment),
            )

    def tarball_name(self) -> str:
        """The filename used for the tarball in the local cache."""
        # We cache tarballs using the filename part of the given URL.
        # However, tarballs produced from tags at GitHub typically only use the
        # version number in the filename. Prefix the project name in that case:
        filename = Path(urlparse(self.url).path).name
        if self.name not in filename:
            filename = f"{self.name}-{filename}"
        return filename

    def tarball_is_cached(self, path: Optional[Path]) -> bool:
        """Return True iff the given path contains this project's tarball."""
        return path is not None and path.is_file() and sha256sum(path) == self.sha256

    def get_tarball(self, cache: pytest.Cache) -> Path:
        """Get this project's tarball. Download if not already cached.

        The cached tarball is keyed by its filename and integrity checked with
        SHA256. Thus a changed URL with the same filename and sha256 checksum
        will still be able to reuse a previously downloaded tarball.

        """
        filename = self.tarball_name()
        # Cannot store Path objects in the pytest cache, only str.
        cached_str = cache.get(f"fawltydeps/{filename}", None)
        if self.tarball_is_cached(cached_str and Path(cached_str)):
            return Path(cached_str)  # already cached

        # Must (re)download
        tarball = Path(cache.mkdir("fawltydeps")) / filename
        logger.info(f"Downloading {self.url!r} to {tarball}...")
        urlretrieve(self.url, tarball)
        if not self.tarball_is_cached(tarball):
            logger.error(f"Failed integrity check after downloading {self.url!r}!")
            logger.error(f"    Downloaded file: {tarball}")
            logger.error(f"    Retrieved SHA256 {sha256sum(tarball)}")
            logger.error(f"     Expected SHA256 {self.sha256}")
            assert False
        cache.set(f"fawltydeps/{filename}", str(tarball))
        return tarball

    def get_unpack_dir(self, tarball: Path, cache: pytest.Cache) -> Path:
        """Get this project's unpack dir. Unpack the given tarball if necessary.

        The unpack dir is where we unpack the project's tarball. It is keyed by
        the sha256 checksum of the tarball, so that we don't risk reusing a
        previously cached unpack dir for a different tarball.
        """
        # We cache unpacked tarballs using the given sha256 sum
        cached_str = cache.get(f"fawltydeps/{self.sha256}", None)
        if cached_str is not None and Path(cached_str).is_dir():
            return Path(cached_str)  # already cached

        # Must unpack
        unpack_dir = Path(cache.mkdir(f"fawltydeps_{self.sha256}"))
        logger.info(f"Unpacking {tarball} to {unpack_dir}...")
        with tarfile.open(tarball) as f:
            f.extractall(unpack_dir)
        assert unpack_dir.is_dir()
        cache.set(f"fawltydeps/{self.sha256}", str(unpack_dir))
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
        tarball = self.get_tarball(cache)
        logger.info(f"Cached tarball is at: {tarball}")
        unpack_dir = self.get_unpack_dir(tarball, cache)

        # Most tarballs contains a single leading directory; descend into it.
        entries = list(unpack_dir.iterdir())
        if len(entries) == 1:
            project_dir = entries[0]
        else:
            project_dir = unpack_dir

        logger.info(f"Unpacked project is at {project_dir}")
        return project_dir


@pytest.mark.parametrize(
    "project, experiment",
    [
        pytest.param(project, experiment, id=experiment.name)
        for project in ThirdPartyProject.collect()
        for experiment in project.experiments
    ],
)
def test_real_project(request, project, experiment):
    project_dir = project.get_project_dir(request.config.cache)
    venv_dir = experiment.get_venv_dir(request.config.cache)

    print(f"Testing real project {project.name!r} under {project_dir}")
    print(f"Project description: {project.description}")
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
