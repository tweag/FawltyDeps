"""Verify behavior of FawltyDeps on real Python projects.

These are bigger integration tests that are not meant to be run on every commit.
We download/extract pinned releases several 3rd-party Python projects, and run
FawltyDeps on them, with hardcoded expectations per project on what FawltyDeps
should find/report.
"""

import hashlib
import sys
import tarfile
from pathlib import Path
from typing import Dict, Iterator, NamedTuple, Optional
from urllib.parse import urlparse
from urllib.request import urlretrieve

import pytest

from fawltydeps import main

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=E1101
else:
    import tomli as tomllib

# These tests will download and unpacks a 3rd-party project before analyzing it.
# These are (slow) integration tests that are disabled by default.
pytestmark = pytest.mark.integration

# Directory with .toml files that define test cases for selected tarballs from
# 3rd-party/real-world projects.
REAL_PROJECTS_DIR = Path(__file__).with_name("real_projects")


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
    """Encapsulate a 3rd-party project to be tested with FawltyDeps.

    This ultimately identifies a tarball containing a 3rd-party Python project,
    and the things we expect FawltyDeps to find when run on that unpacked
    tarball.

    The actual data populating these objects is read from TOML files in
    REAL_PROJECTS_DIR, and the tarballs are downloaded, unpacked, and cached
    by the cached_tarball() fixture above.
    """

    # TODO: Use TOML array of tables (https://toml.io/en/v1.0.0#array-of-tables)
    # to allow the definition of more than one sets of tests per .toml file.
    # The idea is to allow multipled runs of fawltydeps on the project (with
    # different --code and --deps options, as well as other options in the
    # future). This would split this class into two parts, one with the
    # project metadata, and then a list tests, each of which define the
    # necessary fawltydeps options to use, along with the expected
    # .imports, .declared_deps, .undeclared_deps, and .unused_deps.

    toml_path: Path
    name: str
    url: str
    sha256: str
    description: Optional[str] = None
    imports: Optional[Dict[Path, str]] = None
    declared_deps: Optional[Dict[Path, str]] = None
    undeclared_deps: Optional[Dict[Path, str]] = None
    unused_deps: Optional[Dict[Path, str]] = None

    @classmethod
    def parse_from_toml(cls, path: Path) -> "ThirdPartyProject":
        with path.open("rb") as f:
            data = tomllib.load(f)
        # We ultimately _trust_ the .toml files read here, so we can skip all
        # the usual error checking associated with validating external data.
        return cls(
            toml_path=path,
            name=data["project"]["name"],
            description=data["project"].get("description"),
            url=data["project"]["url"],
            sha256=data["project"]["sha256"],
            imports=data.get("imports"),
            declared_deps=data.get("declared_deps"),
            undeclared_deps=data.get("undeclared_deps"),
            unused_deps=data.get("unused_deps"),
        )

    @classmethod
    def collect(cls) -> Iterator["ThirdPartyProject"]:
        for path in REAL_PROJECTS_DIR.iterdir():
            if path.suffix == ".toml":
                yield cls.parse_from_toml(path)


@pytest.mark.parametrize(
    "project",
    [pytest.param(proj, id=proj.name) for proj in ThirdPartyProject.collect()],
)
def test_real_project(cached_tarball, project):
    project_dir = cached_tarball(project.url, project.sha256)
    all_actions = {
        main.Action.LIST_IMPORTS,
        main.Action.LIST_DEPS,
        main.Action.REPORT_UNDECLARED,
        main.Action.REPORT_UNUSED,
    }
    report = main.perform_actions(all_actions, code=project_dir, deps=project_dir)

    if project.imports is not None:
        actual = {name for name, _ in report.imports}
        expect = {name for names in project.imports.values() for name in names}
        assert actual == expect

    if project.declared_deps is not None:
        actual = {name for name, _ in report.declared_deps}
        expect = {name for names in project.declared_deps.values() for name in names}
        assert actual == expect

    if project.undeclared_deps is not None:
        expect = {name for names in project.undeclared_deps.values() for name in names}
        assert report.undeclared_deps == expect

    if project.unused_deps is not None:
        expect = {name for names in project.unused_deps.values() for name in names}
        assert report.unused_deps == expect
