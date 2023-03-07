"""Verify behavior of FawltyDeps on real Python projects.

These are bigger integration tests that are not meant to be run on every commit.
We download/extract pinned releases several 3rd-party Python projects, and run
FawltyDeps on them, with hardcoded expectations per project on what FawltyDeps
should find/report.
"""
import hashlib
import json
import logging
import shlex
import subprocess
import sys
import tarfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, NamedTuple, Optional, Set, Tuple
from urllib.parse import urlparse
from urllib.request import urlretrieve

import pytest

from fawltydeps.extract_declared_dependencies import TomlData

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=E1101
else:
    import tomli as tomllib

JsonData = Dict[str, Any]
logger = logging.getLogger(__name__)

# Each of these tests will download and unpack a 3rd-party project before analyzing it;
# therefore, they're slow and are skipped by default.
pytestmark = pytest.mark.integration

# Directory with .toml files that define test cases for selected tarballs from
# 3rd-party/real-world projects.
REAL_PROJECTS_DIR = Path(__file__).with_name("real_projects")


def run_fawltydeps_json(
    *args: str, venv_dir: Optional[Path], cwd: Optional[Path] = None
) -> JsonData:
    cmd = ["fawltydeps"]
    if venv_dir:
        cmd = [f"{venv_dir}/bin/fawltydeps"]
    proc = subprocess.run(
        cmd + ["--config-file=/dev/null"] + list(args) + ["--json"],
        stdout=subprocess.PIPE,
        check=False,
        cwd=cwd,
    )
    # Check if return code does not indicate error (see main.main for the full list)
    assert proc.returncode in {0, 3, 4}
    return json.loads(proc.stdout)  # type: ignore


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


class Experiment(NamedTuple):
    """A single experiment on a real world project

    Input to the experiment(`args`) is the set of
    command line options to run `fawltydeps` command line tool.

    The expected results of the experiment are `Analysis` results, namely:
    `imports`, `declared_deps`, `undeclared_deps`, `unused_deps`
    """

    name: str
    args: List[str]
    requirements: List[str]
    description: Optional[str] = None
    imports: Optional[List[str]] = None
    declared_deps: Optional[List[str]] = None
    undeclared_deps: Optional[List[str]] = None
    unused_deps: Optional[List[str]] = None

    def venv_script(self, venv_path: Path):
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

    @classmethod
    def parse_from_toml(cls, name: str, data: TomlData) -> "Experiment":
        return cls(
            name=name,
            args=data["args"],
            requirements=data.get("requirements", []),
            description=data.get("description"),
            imports=data.get("imports"),
            declared_deps=data.get("declared_deps"),
            undeclared_deps=data.get("undeclared_deps"),
            unused_deps=data.get("unused_deps"),
        )

    def verify_analysis_json(self, analysis: JsonData) -> None:
        """Assert that the given JSON analysis matches our expectations."""

        def json_names(data: List[JsonData]) -> Set[str]:
            return {d["name"] for d in data}

        if self.imports is not None:
            print(f"{self.name}: Checking imports")
            assert set(self.imports) == json_names(analysis["imports"])
        else:
            print(f"{self.name}: No imports to check")

        if self.declared_deps is not None:
            print(f"{self.name}: Checking declared dependencies")
            assert set(self.declared_deps) == json_names(analysis["declared_deps"])
        else:
            print(f"{self.name}: No declared dependencies")

        if self.undeclared_deps is not None:
            print(f"{self.name}: Checking undeclared dependencies")
            assert set(self.undeclared_deps) == json_names(analysis["undeclared_deps"])
        else:
            print(f"{self.name}: No undeclared dependencies to check")

        if self.unused_deps is not None:
            print(f"{self.name}: Checking unused dependencies")
            assert set(self.unused_deps) == json_names(analysis["unused_deps"])
        else:
            print(f"{self.name}: No unused dependencies to check")

    def venv_hash(self):
        """
        Returns a hash that depends on the venv script and python version.

        The installation script will change if the code to setup the venv on
        `venv_script` changes or if the requirements field of the experiment
        changes. It will also be different for different Python versions.
        The Python version currently used to run the tests is used to compute
        the hash and create the venv.
        """
        dummy_script = self.venv_script(Path("/dev/null"))
        py_version = f"{sys.version_info.major},{sys.version_info.major}"
        script_and_version_bytes = ("".join(dummy_script) + py_version).encode()
        return hashlib.sha256(script_and_version_bytes).hexdigest()

    def get_venv_dir(self, cache: pytest.Cache) -> Path:
        """
        Get this venv's dir and create it if necessary.

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
        venv_script = self.venv_script(venv_dir)
        subprocess.run(
            " && ".join(venv_script),
            check=True,  # fail if any of the commands fail
            shell=True,  # pass multiple shell commands to the subprocess
        )
        # Make sure the venv has been installed
        assert Path(venv_dir, ".installed").is_file()
        cache.set(f"fawltydeps/{self.venv_hash()}", str(venv_dir))
        return venv_dir

    @contextmanager
    def venv_with_fawltydeps(self, cache: pytest.Cache) -> Iterator[Path]:
        """Provide this experiments's venv with FawltyDeps installed within.

        Provide a context in which the FawltyDeps version located in the current
        working directory is installed in editable mode. Uninstall FawltyDeps
        upon exiting the context, so that the venv_dir is ready for the next
        test (which may be run from a different current working directory).
        """
        venv_dir = self.get_venv_dir(cache)
        # setup: install editable fawltydeps
        subprocess.run([f"{venv_dir}/bin/pip", "install", "-e", "./"], check=True)
        try:
            yield venv_dir
        finally:
            # teardown: uninstall fawltydeps
            subprocess.run(
                [f"{venv_dir}/bin/pip", "uninstall", "-y", "fawltydeps"], check=True
            )


class ThirdPartyProject(NamedTuple):
    """Encapsulate a 3rd-party project to be tested with FawltyDeps.

    This ultimately identifies a tarball containing a 3rd-party Python project,
    and the things we expect FawltyDeps to find when run on that unpacked
    tarball.

    The actual data populating these objects is read from TOML files in
    REAL_PROJECTS_DIR, and the tarballs are downloaded, unpacked, and cached
    by the methods below.
    """

    toml_path: Path
    name: str
    url: str
    sha256: str
    experiments: List[Experiment]
    description: Optional[str] = None

    @classmethod
    def parse_from_toml(cls, path: Path) -> "ThirdPartyProject":
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            print(f"Error occurred while parsing file: {path}")
            raise

        # We ultimately _trust_ the .toml files read here, so we can skip all
        # the usual error checking associated with validating external data.
        project_name = data["project"]["name"]
        return cls(
            toml_path=path,
            name=project_name,
            description=data["project"].get("description"),
            url=data["project"]["url"],
            sha256=data["project"]["sha256"],
            experiments=[
                Experiment.parse_from_toml(f"{project_name}:{name}", experiment_data)
                for name, experiment_data in data["experiments"].items()
            ],
        )

    @classmethod
    def collect(cls) -> Iterator[Tuple["ThirdPartyProject", Experiment]]:
        for path in filter(lambda p: p.suffix == ".toml", REAL_PROJECTS_DIR.iterdir()):
            project = cls.parse_from_toml(path)
            for experiment in project.experiments:
                yield (project, experiment)

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
        pytest.param(proj, experiment, id=experiment.name)
        for proj, experiment in ThirdPartyProject.collect()
    ],
)
def test_real_project(request, project, experiment):
    project_dir = project.get_project_dir(request.config.cache)
    with experiment.venv_with_fawltydeps(request.config.cache) as venv_dir:
        analysis = run_fawltydeps_json(
            *experiment.args,
            venv_dir=venv_dir,
            cwd=project_dir,
        )

    print(f"Checking experiment {experiment.name} for project under {project_dir}...")
    experiment.verify_analysis_json(analysis)
