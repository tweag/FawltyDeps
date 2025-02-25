"""Common helpers shared between test_real_project and test_sample_projects."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from enum import Flag, auto
from functools import reduce
from operator import or_ as bitwise_or
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Set, Type
from urllib.parse import urlparse
from urllib.request import urlretrieve

import pytest

from fawltydeps.main import Analysis
from fawltydeps.types import TomlData

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

JsonData = Dict[str, Any]

PACKAGES_TOML_PATH = Path(__file__).with_name("python_packages.toml")

logger = logging.getLogger(__name__)


class Compatibility(Flag):
    """Represent a project/experiment's platform compatibility.

    By default, we assume tests are compatible with all platforms (represented
    as the bitwise OR of all compatibility flags, as returned from .all()), but
    this can be limited to any combination of the flag values below.

    This compatibility can then be against the current platform by bitwise AND-
    ing it against the Compatibility value corresponding to the current platform
    (as returned from .current()).
    """

    LINUX = auto()
    MACOS = auto()
    WINDOWS = auto()
    POSIX = LINUX | MACOS

    @classmethod
    def current(cls) -> Compatibility:
        """Return the current platform as a compatibility flag."""
        if sys.platform.startswith("win"):
            return cls.WINDOWS
        if sys.platform.startswith("darwin"):
            return cls.MACOS
        if sys.platform.startswith("linux"):
            return cls.LINUX
        raise RuntimeError(f"Unexpected platform {sys.platform!r}!")

    @classmethod
    def all(cls) -> Compatibility:
        """Return the combination of all compatibility flags."""
        # Iterate over class to get individual flag values, and combine them all
        values: Iterator[Compatibility] = iter(cls)
        return reduce(bitwise_or, values)

    @classmethod
    def parse(cls, value: Optional[str]) -> Compatibility:
        """Parse the given string into a compatibility flag.

        If the given value is None, return the combination of all flags.
        """
        return cls.all() if value is None else Compatibility.__members__[value]


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
        urlretrieve(self.url, tarball_path)  # noqa: S310
        if not self.is_cached(tarball_path):
            logger.error(f"Failed integrity check after downloading {self.url!r}!")
            logger.error(f"    Downloaded file: {tarball_path}")
            logger.error(f"    Retrieved SHA256 {sha256sum(tarball_path)}")
            logger.error(f"     Expected SHA256 {self.sha256}")
            pytest.fail(f"Failed integrity check after downloading {self.url!r}!")
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

    requirements: List[str]  # PEP 508 requirements, passed to (uv) pip install

    @staticmethod
    def _venv_python(venv_path: Path) -> Path:
        """Return path to Python executable inside the given venv."""
        if sys.platform.startswith("win"):  # Windows
            return venv_path / "Scripts" / "python.exe"
        # Assume POSIX
        return venv_path / "bin" / "python"

    def _venv_commands_pip(
        self, venv_path: Path, python_exe: str
    ) -> Iterator[List[str]]:
        """Yield pip commands to run in order to create/populate venv_path."""
        venv_python = str(self._venv_python(venv_path))
        yield [python_exe, "-m", "venv", str(venv_path)]
        yield [venv_python, "-m", "pip", "install", "--upgrade", "pip"]
        for req in self.requirements:
            yield [venv_python, "-m", "pip", "install", "--no-deps", req]

    def _venv_commands_uv(
        self, venv_path: Path, python_exe: str, uv_exe: str
    ) -> Iterator[List[str]]:
        """Yield uv commands to run in order to create/populate venv_path."""
        venv_python = str(self._venv_python(venv_path))
        yield [uv_exe, "venv", "--python", python_exe, str(venv_path)]
        for req in self.requirements:
            yield [uv_exe, "pip", "install", "--python", venv_python, "--no-deps", req]

    def venv_commands(
        self,
        venv_path: Path,
        python_exe: Optional[str] = None,
        *,
        prefer_uv_if_available: Optional[bool] = True,
    ) -> Iterator[List[str]]:
        """Yield commands to run in order to create and populate the given venv.

        The commands are yielded as argv-style lists of strings. The commands
        must be run in sequence, and each command must return successfully in
        order for the venv to be considered successfully created.
        """
        uv_exe = shutil.which("uv") if prefer_uv_if_available else None
        if python_exe is None:  # Default to current Python executable
            python_exe = sys.executable

        if uv_exe is not None:
            yield from self._venv_commands_uv(venv_path, python_exe, uv_exe)
        else:
            yield from self._venv_commands_pip(venv_path, python_exe)

    def venv_hash(self) -> str:
        """Returns a hash that depends on the venv script and Python version.

        The venv script will change if the code to setup the venv in
        venv_commands() changes, or if the requirements of the experiment
        changes. It will also be different for different Python versions.
        """
        dummy_script = [
            " ".join(argv) for argv in self.venv_commands(Path(os.devnull), "python")
        ] + [f"# Python {sys.version_info.major}.{sys.version_info.minor}"]
        return hashlib.sha256("\n".join(dummy_script).encode()).hexdigest()

    def __call__(self, cache: pytest.Cache) -> Path:
        """Get this venv's dir from cache, or create it if necessary.

        The venv_dir is where we install the dependencies of the current
        experiment. It is keyed by the sha256 checksum of the commands we use
        to create and populate the venv with this experiment's requirements.
        This way, we don't risk reusing a previously cached venv if the commands
        or the requirements has changed.
        """
        # We cache venv dirs using the hash from create_venv_hash() as key
        cached_str = cache.get(str(Path("fawltydeps", self.venv_hash())), None)
        if cached_str is not None and Path(cached_str, ".installed").is_file():
            return Path(cached_str)  # already cached

        # Must run the commands to set up the venv
        venv_dir = Path(cache.mkdir(f"fawltydeps_venv_{self.venv_hash()}"))
        logger.info(f"Creating venv at {venv_dir}...")

        shutil.rmtree(venv_dir)  # start from a clean slate
        for argv in self.venv_commands(venv_dir):
            subprocess.run(argv, check=True)  # fail if any of the commands fail
        (venv_dir / ".installed").touch()  # touch install marker on no errors
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
    - Optional compatibility flag to control where this experiment can be run.
      If this is given, and does not include the current platform, then the
      experiment will be skipped. When not given, the experiment inherits the
      compatibility of the parent project.
    - A list of requirements, to be installed into a virtualenv and made
      available to FawltyDeps when this experiment is run
      (see CachedExperimentVenv for details).
    - A set of expectations on the resulting Analysis object, to be verified
      after the FawltyDeps has been run (see AnalysisExpectations for details).
    """

    name: str
    description: Optional[str]
    compatibility: Optional[Compatibility]
    requirements: List[str]
    expectations: AnalysisExpectations

    @staticmethod
    def _init_args_from_toml(name: str, data: TomlData) -> Dict[str, Any]:
        """Extract members from TOML into kwargs for a subclass constructor."""
        description = data.get("description")
        compat = data.get("compatibility")
        return dict(
            name=name,
            description=None if description is None else dedent(description),
            requirements=data.get("requirements", []),
            compatibility=None if compat is None else Compatibility.parse(compat),
            expectations=AnalysisExpectations.from_toml(data),
        )

    @classmethod
    @abstractmethod
    def from_toml(cls, name: str, data: TomlData) -> BaseExperiment:
        """Create an instance from TOML data."""
        raise NotImplementedError

    def maybe_skip(self, project: BaseProject):
        compatibility = self.compatibility or project.compatibility
        if not compatibility & Compatibility.current():  # Failed compat check
            pytest.skip(
                "Test not compatible with current system"
                f" ({compatibility} != {Compatibility.current()})"
            )

    def get_venv_dir(self, cache: pytest.Cache) -> Path:
        """Get this venv's dir and create it if necessary."""
        return CachedExperimentVenv(self.requirements)(cache)


@dataclass
class BaseProject(ABC):
    """Encapsulate a Python project to be tested with FawltyDeps.

    This represents a project on which we want to run FawltyDeps in one or more
    experiments. It has at least:
    - A name and optional description, for documentation purposes.
    - Optional compatibility flag to control where this project can be run. If
      this is given, and does not include the current platform, then all of the
      experiments in this project will be skipped by default (unless overridden
      by the experiment itself). By default, the project is assumed to be
      compatible with all platforms.
    - A list of experiments (see BaseExperiment above), describing one or more
      scenarios for running FawltyDeps on this project, and what results to
      expect in those scenarios.
    """

    name: str
    description: Optional[str]
    compatibility: Compatibility
    experiments: List[BaseExperiment]

    @staticmethod
    def _init_args_from_toml(
        toml_data: TomlData,
        ExperimentClass: Type[BaseExperiment],  # noqa: N803
    ) -> Dict[str, Any]:
        """Extract members from TOML into kwargs for a subclass constructor."""
        # We ultimately _trust_ the .toml files read here, so we can skip all
        # the usual error checking associated with validating external data.
        project_name = toml_data["project"]["name"]
        return dict(
            name=project_name,
            description=dedent(toml_data["project"].get("description")),
            compatibility=Compatibility.parse(
                toml_data["project"].get("compatibility")
            ),
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
