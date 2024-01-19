"""Common helpers shared between test_real_project and test_sample_projects."""
from __future__ import annotations

import hashlib
import logging
import os
import shlex
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set, Type
from urllib.parse import urlparse
from urllib.request import urlretrieve

import pytest

from fawltydeps.main import Analysis
from fawltydeps.types import TomlData

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=E1101
else:
    import tomli as tomllib

JsonData = Dict[str, Any]

PACKAGES_TOML_PATH = Path(__file__).with_name("python_packages.toml")

logger = logging.getLogger(__name__)


@dataclass
class TarballPackage:
    """Encapsulate a Python tarball package.

    This object fields are expected to be populated either from:
    - A single toml file containing multiple tarballs info
    - Multiple TOML files in REAL_PROJECTS_DIR
    The tarballs are downloaded and cached by the methods below.
    """

    url: str
    sha256: str
    # If the following is given, we'll make sure the cached tarball has this
    # somewhere in its filename (helps with version-only tarballs from GitHub).
    filename_must_include: Optional[str] = None

    @classmethod
    def collect_from_toml(cls, path: Path) -> Iterator[TarballPackage]:
        """Parse information on all available tarball packages in a toml file."""
        tarballs = parse_toml(path)
        for info in tarballs.values():
            yield cls(url=info["url"], sha256=info["sha256"])

    @classmethod
    def get_tarballs(cls, cache: pytest.Cache, path: Path = PACKAGES_TOML_PATH):
        """Get (or download) tarballs of packages defined in the toml file."""
        for tarball_package in cls.collect_from_toml(path):
            tarball_package.get(cache)

    def tarball_name(self) -> str:
        """The filename used for the tarball in the local cache."""
        # We cache tarballs using the filename part of the given URL.
        # However, tarballs produced from tags at GitHub typically only use the
        # version number in the filename. Prefix the project name in that case:
        filename = Path(urlparse(self.url).path).name
        if self.filename_must_include and self.filename_must_include not in filename:
            filename = f"{self.filename_must_include}-{filename}"
        return filename

    def is_cached(self, path: Optional[Path]) -> bool:
        """Return True iff the given path contains this package's tarball."""
        return path is not None and path.is_file() and sha256sum(path) == self.sha256

    def get(self, cache: pytest.Cache) -> Path:
        """Get this package's tarball. Download if not already cached.

        The cached tarball is keyed by its filename and integrity checked with
        SHA256. Thus a changed URL with the same filename and sha256 checksum
        will still be able to reuse a previously downloaded tarball.

        """
        # Cannot store Path objects in the pytest cache, only str.
        cached_str = cache.get(self.cache_key, None)
        if self.is_cached(cached_str and Path(cached_str)):
            return Path(cached_str)  # already cached

        # Must (re)download
        tarball_path = self.tarball_path(cache)
        logger.info(f"Downloading {self.url!r} to {tarball_path}...")
        urlretrieve(self.url, tarball_path)
        if not self.is_cached(tarball_path):
            logger.error(f"Failed integrity check after downloading {self.url!r}!")
            logger.error(f"    Downloaded file: {tarball_path}")
            logger.error(f"    Retrieved SHA256 {sha256sum(tarball_path)}")
            logger.error(f"     Expected SHA256 {self.sha256}")
            assert False
        cache.set(self.cache_key, str(tarball_path))
        return tarball_path

    @property
    def cache_key(self) -> str:
        return str(Path("fawltydeps", self.tarball_name()))

    def tarball_path(self, cache: pytest.Cache) -> Path:
        return self.cache_dir(cache) / self.tarball_name()

    @classmethod
    def cache_dir(cls, cache: pytest.Cache) -> Path:
        """Return the directory of the cache used for tarball packages."""
        return Path(cache.mkdir("fawltydeps"))


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
        if sys.platform.startswith("win"):
            pip_path = venv_path / "Scripts" / "pip.exe"
            python_path = venv_path / "Scripts" / "python.exe"
            return (
                [
                    f"rd /s /q {venv_path}",
                    f"{sys.executable} -m venv {venv_path}",
                    f"{python_path} -m pip install --upgrade pip",
                ]
                + [
                    f'{python_path} -m pip install --no-deps "{req}"'
                    for req in self.requirements
                ]
                + [
                    f"type nul > {venv_path / '.installed'}",
                ]
            )

        pip_path = venv_path / "bin" / "pip"
        return (
            [
                f"rm -rf {venv_path}",
                f"{sys.executable} -m venv {venv_path}",
                f"{pip_path} install --upgrade pip",
            ]
            + [
                f"{pip_path} install --no-deps {shlex.quote(req)}"
                for req in self.requirements
            ]
            + [
                f"touch {venv_path / '.installed'}",
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
        dummy_script = self.venv_script_lines(Path(os.devnull))
        py_version = f"{sys.version_info.major},{sys.version_info.minor}"
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
        cached_str = cache.get(str(Path("fawltydeps", self.venv_hash())), None)
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
        cache.set(str(Path("fawltydeps", self.venv_hash())), str(venv_dir))
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
    def from_toml(cls, data: TomlData) -> AnalysisExpectations:
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
    - Optional posix_only or windows_only flags to control where this experiment
      can be run. If one of these flags is given, and does not match the current
      platform, the experiment will be skipped.
    - A list of requirements, to be installed into a virtualenv and made
      available to FawltyDeps when this experiment is run
      (see CachedExperimentVenv for details).
    - A set of expectations on the resulting Analysis object, to be verified
      after the FawltyDeps has been run (see AnalysisExpectations for details).
    """

    name: str
    description: Optional[str]
    posix_only: bool
    windows_only: bool
    requirements: List[str]
    expectations: AnalysisExpectations

    @staticmethod
    def _init_args_from_toml(name: str, data: TomlData) -> Dict[str, Any]:
        """Extract members from TOML into kwargs for a subclass constructor."""
        description = data.get("description")
        return dict(
            name=name,
            description=None if description is None else dedent(description),
            requirements=data.get("requirements", []),
            posix_only=data.get("posix_only", False),
            windows_only=data.get("windows_only", False),
            expectations=AnalysisExpectations.from_toml(data),
        )

    @classmethod
    @abstractmethod
    def from_toml(cls, name: str, data: TomlData) -> BaseExperiment:
        """Create an instance from TOML data."""
        raise NotImplementedError

    def maybe_skip(self, project: BaseProject):
        posix_only = self.posix_only or project.posix_only
        windows_only = self.windows_only or project.windows_only
        assert not (posix_only and windows_only)  # cannot have both!
        if posix_only and sys.platform.startswith("win"):
            pytest.skip("POSIX-only experiment, but we're on Windows")
        elif windows_only and not sys.platform.startswith("win"):
            pytest.skip("Windows-only experiment, but we're on POSIX")

    def get_venv_dir(self, cache: pytest.Cache) -> Path:
        """Get this venv's dir and create it if necessary."""
        return CachedExperimentVenv(self.requirements)(cache)


@dataclass
class BaseProject(ABC):
    """Encapsulate a Python project to be tested with FawltyDeps.

    This represents a project on which we want to run FawltyDeps in one or more
    experiments. It has at least:
    - A name and optional description, for documentation purposes.
    - Optional posix_only or windows_only flags to signal where this project
      can be run. If one of these flags is given, and does not match the current
      platform, all experiments in this project will be skipped.
    - A list of experiments (see BaseExperiment above), describing one or more
      scenarios for running FawltyDeps on this project, and what results to
      expect in those scenarios.
    """

    name: str
    description: Optional[str]
    posix_only: bool
    windows_only: bool
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
            description=dedent(toml_data["project"].get("description")),
            posix_only=toml_data["project"].get("posix_only", False),
            windows_only=toml_data["project"].get("windows_only", False),
            experiments=[
                ExperimentClass.from_toml(f"{project_name}:{name}", data)
                for name, data in toml_data["experiments"].items()
            ],
        )

    @classmethod
    @abstractmethod
    def collect(cls) -> Iterator[BaseProject]:
        """Find and generate all projects in this test suite."""
        raise NotImplementedError


def parse_toml(toml_path: Path) -> TomlData:
    try:
        with toml_path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError:
        print(f"Error occurred while parsing file: {toml_path}")
        raise


def sha256sum(path: Path):
    """Calculate the SHA256 checksum of the given file.

    Read the file in 64kB blocks while calculating the checksum, and return
    the hex-encoded digest.
    """
    sha256 = hashlib.sha256()
    BLOCK_SIZE = 64 * 1024
    with path.open("rb") as f:
        for block in iter(lambda: f.read(BLOCK_SIZE), b""):
            sha256.update(block)
    return sha256.hexdigest()
