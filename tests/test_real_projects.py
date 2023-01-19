"""Verify behavior of FawltyDeps on real Python projects.

These are bigger integration tests that are not meant to be run on every commit.
We download/extract pinned releases several 3rd-party Python projects, and run
FawltyDeps on them, with hardcoded expectations per project on what FawltyDeps
should find/report.
"""

import hashlib
import tarfile
from pathlib import Path
from typing import NamedTuple, Optional, Set, Tuple
from urllib.parse import urlparse
from urllib.request import urlretrieve

import pytest

from fawltydeps import main

# These tests will download and unpacks a 3rd-party project before analyzing it.
# These are (slow) integration tests that are disabled by default.
pytestmark = pytest.mark.integration


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


@pytest.fixture
def cached_tarball(request):
    """Cache unpacked tarballs, identified by URL and SHA256 checksum.

    This makes use of the caching mechanism in pytest, documented on
    https://docs.pytest.org/en/7.1.x/reference/reference.html#config-cache.

    The caching happens in two stages. First we cache the downloaded tarball,
    then we also cache the unpacked tarball.

    The cached tarball is keyed by its filename and integrity checked with
    SHA256. Thus a changed URL with the same filename and sha256 checksum will
    still be able to reuse a previously downloaded tarball.

    The unpacked tarball is keyed by the given sha256. Thus an updated sha256
    will cause (a new download and) a new unpack.

    The actual integrity check only happens immediately after a download, hence
    we assume that the local cache (both the downloaded tarball, as well as the
    unpacked tarball) is uncorrupted and immutable.
    """

    def _tarball_is_cached(path: Optional[Path], sha256: str) -> bool:
        return path is not None and path.is_file() and sha256sum(path) == sha256

    def _get_tarball(url: str, sha256: str) -> Path:
        # We cache tarballs using the filename part of the given URL
        filename = Path(urlparse(url).path).name
        # Cannot store Path objects in request.config.cache, only str.
        cached_str = request.config.cache.get(f"fawltydeps/{filename}", None)
        if _tarball_is_cached(cached_str and Path(cached_str), sha256):
            return Path(cached_str)

        # Must (re)download
        tarball = Path(request.config.cache.mkdir("fawltydeps")) / filename
        print(f"Downloading {url!r} to {tarball}...")
        urlretrieve(url, tarball)
        if not _tarball_is_cached(tarball, sha256):
            print(f"Failed integrity check after downloading {url!r}!")
            print(f"    Downloaded file: {tarball}")
            print(f"    Retrieved SHA256 {sha256sum(tarball)}")
            print(f"     Expected SHA256 {sha256}")
            assert False
        request.config.cache.set(f"fawltydeps/{filename}", str(tarball))
        return tarball

    def _unpack_dir_is_cached(path: Optional[Path]) -> bool:
        return path is not None and path.is_dir()

    def _get_unpack_dir(tarball: Path, sha256: str) -> Path:
        # We cache unpacked tarballs using the given sha256 sum
        cached_str = request.config.cache.get(f"fawltydeps/{sha256}", None)
        if _unpack_dir_is_cached(cached_str and Path(cached_str)):
            return Path(cached_str)

        # Must unpack
        unpack_dir = Path(request.config.cache.mkdir(f"fawltydeps_{sha256}"))
        print(f"Unpacking {tarball} to {unpack_dir}...")
        with tarfile.open(tarball) as f:
            f.extractall(unpack_dir)
        assert _unpack_dir_is_cached(unpack_dir)
        request.config.cache.set(f"fawltydeps/{sha256}", str(unpack_dir))
        return unpack_dir

    def _download_and_unpack(url: str, sha256: str) -> Path:
        tarball = _get_tarball(url, sha256)
        print(f"Cached tarball is at: {tarball}")
        unpack_dir = _get_unpack_dir(tarball, sha256)

        # Most tarballs contains a single leading directory; descend into it.
        entries = list(unpack_dir.iterdir())
        if len(entries) == 1:
            unpack_dir = entries[0]

        print(f"Unpacked tarball is at {unpack_dir}")
        return unpack_dir

    return _download_and_unpack


class ThirdPartyProject(NamedTuple):
    """Excapsulating a 3rd-party project to be tested with FawltyDeps.

    A tarball containing a 3rd-party Python project, and the things we expect
    FawltyDeps to find within.
    """

    name: str
    url: str
    sha256: str
    imports: Set[str] = set()
    deps: Set[str] = set()
    undeclared: Set[str] = set()
    unused: Set[str] = set()


@pytest.fixture
def run_fawltydeps_on_project(cached_tarball, capsys):
    def _inner(project: ThirdPartyProject, action: main.Action) -> Tuple[str, str]:
        d = cached_tarball(project.url, project.sha256)
        capsys.readouterr()  # reset stdout/stderr
        main.perform_actions({action}, code=d, deps=d)
        stdout, stderr = capsys.readouterr()
        return stdout, stderr

    return _inner


projects_to_test = [
    # A small/trivial project that has no real dependencies
    ThirdPartyProject(
        name="left-pad",
        url=(
            "https://files.pythonhosted.org/packages/a0/34/cd668981dc6818d8a39f"
            "1185af8113268ddc71d99b0ba4aa8ceee2a123e7/left-pad-0.0.3.tar.gz"
        ),
        sha256="b842b81fcf157ca09b1e0036c5876295fdfd097640aa85d37f988857eec64654",
        imports={"distutils", "setuptools"},  # from setup.py
        undeclared={"setuptools"},  # TODO: Is this a _real_ dep!?
    ),
    # One of the most heavily-used third-party packages in the Python world
    ThirdPartyProject(
        name="requests",
        url="https://github.com/psf/requests/archive/refs/tags/v2.28.2.tar.gz",
        sha256="375d6bb6b73af27c69487dcf1df51659a8ee7428420caff21253825fb338ce10",
        imports={
            "base64",
            "BaseHTTPServer",
            "calendar",
            "certifi",
            "chardet",
            "charset_normalizer",
            "codecs",
            "collections",
            "contextlib",
            "copy",
            "cryptography",
            "cStringIO",
            "datetime",
            "dummy_threading",
            "encodings",
            "filecmp",
            "hashlib",
            "http",
            "idna",
            "io",
            "json",
            "logging",
            "multiprocessing",
            "netrc",
            "OpenSSL",
            "os",
            "pickle",
            "platform",
            "pygments",
            "pytest",
            "re",
            "requests",
            "select",
            "setuptools",
            "SimpleHTTPServer",
            "simplejson",
            "socket",
            "ssl",
            "StringIO",
            "struct",
            "sys",
            "tarfile",
            "tempfile",
            "tests",
            "threading",
            "time",
            "trustme",
            "urllib",
            "urllib3",
            "warnings",
            "winreg",
            "zipfile",
        },
        deps={"chardet", "pysocks", "sphinx"},
        undeclared={
            "BaseHTTPServer",
            "certifi",
            "charset_normalizer",
            "cryptography",
            "cStringIO",
            "idna",
            "OpenSSL",
            "pygments",
            "pytest",
            "requests",
            "setuptools",
            "SimpleHTTPServer",
            "simplejson",
            "StringIO",
            "tests",
            "trustme",
            "urllib3",
        },
        unused={"pysocks", "sphinx"},
    ),
]


@pytest.mark.parametrize(
    "project", [pytest.param(project, id=project.name) for project in projects_to_test]
)
def test_list_imports(run_fawltydeps_on_project, project):
    out, err = run_fawltydeps_on_project(project, main.Action.LIST_IMPORTS)
    actual = {line.split(":", 1)[0] for line in out.splitlines()}
    assert actual == project.imports
    assert not err


@pytest.mark.parametrize(
    "project", [pytest.param(project, id=project.name) for project in projects_to_test]
)
def test_list_deps(run_fawltydeps_on_project, project):
    out, err = run_fawltydeps_on_project(project, main.Action.LIST_DEPS)
    actual = {line.split(":", 1)[0] for line in out.splitlines()}
    assert actual == project.deps
    assert not err


@pytest.mark.parametrize(
    "project", [pytest.param(project, id=project.name) for project in projects_to_test]
)
def test_report_undeclared(run_fawltydeps_on_project, project):
    out, err = run_fawltydeps_on_project(project, main.Action.REPORT_UNDECLARED)
    lines = out.splitlines()
    if project.undeclared:  # There is something to report
        assert lines.pop(0) == "These imports are not declared as dependencies:"
    assert all(line.startswith("- ") or line.startswith("    ") for line in lines)
    actual = set(line[2:-14] for line in lines if line.startswith("- "))
    assert actual == project.undeclared
    assert not err


@pytest.mark.parametrize(
    "project", [pytest.param(project, id=project.name) for project in projects_to_test]
)
def test_report_unused(run_fawltydeps_on_project, project):
    out, err = run_fawltydeps_on_project(project, main.Action.REPORT_UNUSED)
    lines = out.splitlines()
    if project.unused:  # There is something to report
        assert lines.pop(0) == "These dependencies are not imported in your code:"
    assert all(line.startswith("- ") for line in lines)
    actual = set(line[2:] for line in lines)
    assert actual == project.unused
    assert not err
