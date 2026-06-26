"""Verify that the full (dotted) import path is used to detect bad deps.

FawltyDeps historically tracked imports and dependencies by their top-level
component only (e.g. "google"). That is insufficient when several distributions
share an import prefix, as is the case for PEP 420 namespace packages such as
`google-cloud-storage` (providing `google.cloud.storage`) and
`google-cloud-bigquery` (providing `google.cloud.bigquery`). These tests pin down
the behavior that distinguishes such packages by their full import path.
"""

from pathlib import Path, PurePosixPath
from textwrap import dedent

import pytest

from fawltydeps.check import calculate_undeclared, calculate_unused
from fawltydeps.extract_imports import parse_code
from fawltydeps.packages import (
    IdentityMapping,
    LocalPackageResolver,
    Package,
    _modules_from_files,
    _provided_imports,
    module_matches,
)
from fawltydeps.settings import Settings
from fawltydeps.types import (
    DeclaredDependency,
    Location,
    ParsedImport,
    PyEnvSource,
    UndeclaredDependency,
    UnusedDependency,
)

# --- module_matches: prefix/ancestor matching of dotted import paths ---


@pytest.mark.parametrize(
    ("imported", "provided", "expect"),
    [
        ("foo", "foo", True),
        ("foo.bar", "foo", True),  # submodule of a provided top-level package
        ("foo.bar.baz", "foo.bar", True),  # deeper submodule
        ("foo", "foo.bar", False),  # a parent namespace is not "provided"
        ("foobar", "foo", False),  # prefix string, but not a module ancestor
        ("google.cloud.bigquery", "google.cloud.storage", False),  # the headline case
        ("google.cloud.storage", "google.cloud.storage", True),
        ("google.cloud.storage.blob", "google.cloud.storage", True),
    ],
)
def test_module_matches(imported, provided, expect):
    assert module_matches(imported, provided) is expect


# --- Inferring a distribution's provided modules from its file list ---


class FakeDist:
    """A minimal stand-in for an importlib_metadata Distribution."""

    def __init__(self, files, top_level=None):
        self.files = [PurePosixPath(f) for f in files]
        self._top_level = top_level

    def read_text(self, filename):
        return self._top_level if filename == "top_level.txt" else None


@pytest.mark.parametrize(
    ("files", "expect"),
    [
        pytest.param(
            ["numpy/__init__.py", "numpy/linalg/__init__.py", "numpy/core.py"],
            {"numpy"},
            id="regular_package__reports_topmost_package_only",
        ),
        pytest.param(
            ["six.py"],
            {"six"},
            id="single_module__reports_module",
        ),
        pytest.param(
            ["google/cloud/storage/__init__.py", "google/cloud/storage/blob.py"],
            {"google.cloud.storage"},
            id="namespace_package__descends_to_regular_package",
        ),
        pytest.param(
            ["google/cloud/bigquery/__init__.py", "google/cloud/bigquery/client.py"],
            {"google.cloud.bigquery"},
            id="other_namespace_package__yields_distinct_full_path",
        ),
        pytest.param(
            ["foo-stubs/__init__.pyi", "foo-stubs/bar.pyi"],
            {"foo-stubs"},
            id="stub_only_package__keeps_stubs_suffix",
        ),
        pytest.param(
            ["pkg-1.0.dist-info/RECORD", "pkg-1.0.dist-info/METADATA"],
            set(),
            id="dist_info_files__are_ignored",
        ),
    ],
)
def test_modules_from_files(files, expect):
    assert _modules_from_files(FakeDist(files)) == expect


def test_provided_imports__refines_declared_top_level_into_full_path():
    dist = FakeDist(
        ["google/cloud/storage/__init__.py", "google/cloud/storage/blob.py"],
        top_level="google\n",
    )
    assert _provided_imports(dist) == ["google.cloud.storage"]


def test_provided_imports__falls_back_to_top_level_when_no_files():
    # An installed dist without a usable RECORD (no .files) should still resolve
    # to its declared top-level name(s).
    dist = FakeDist([], top_level="google\n")
    assert _provided_imports(dist) == ["google"]


# --- Package matching against full import paths ---


def test_package_provides__namespace_package_does_not_cover_sibling():
    storage = Package("google-cloud-storage", {"google.cloud.storage"}, IdentityMapping)
    assert storage.provides("google.cloud.storage")
    assert storage.provides("google.cloud.storage.blob")
    assert not storage.provides("google.cloud.bigquery")
    assert not storage.provides("google.cloud")  # bare namespace is not provided


def test_package_is_used__matches_submodule_imports():
    pkg = Package("numpy", {"numpy"}, IdentityMapping)
    assert pkg.is_used(["numpy.linalg"])
    assert not pkg.is_used(["numpyfoo"])


# --- Parsing records the fully-qualified import paths ---


def test_parse_code__from_import_records_qualified_submodules():
    code = "from google.cloud import storage, bigquery\n"
    [imp] = list(parse_code(code, source=Location("<stdin>")))
    assert imp.name == "google"  # top-level, as shown to the user
    assert set(imp.qualified) == {
        "google.cloud.storage",
        "google.cloud.bigquery",
    }
    assert set(imp.match_keys) == {
        "google.cloud.storage",
        "google.cloud.bigquery",
    }


def test_parse_code__plain_dotted_import_records_full_path():
    code = "import google.cloud.bigquery\n"
    [imp] = list(parse_code(code, source=Location("<stdin>")))
    assert imp.name == "google"
    assert imp.qualified == ("google.cloud.bigquery",)


def test_parse_code__star_import_falls_back_to_module():
    code = "from google.cloud import *\n"
    [imp] = list(parse_code(code, source=Location("<stdin>")))
    assert imp.qualified == ("google.cloud",)


# --- End-to-end undeclared / unused detection across a shared namespace ---


def _dep(name):
    return DeclaredDependency(name, Location("requirements.txt"))


def _import(*qualified, name=None, lineno=1):
    return ParsedImport(
        name=name or qualified[0].split(".", 1)[0],
        source=Location("code.py", lineno=lineno),
        qualified=tuple(qualified),
    )


def test_undeclared__sibling_namespace_import_is_flagged():
    # We declare google-cloud-storage but import google.cloud.bigquery. Even
    # though both share the "google" prefix, the bigquery import is undeclared.
    resolved = {
        "google-cloud-storage": Package(
            "google-cloud-storage", {"google.cloud.storage"}, IdentityMapping
        ),
    }
    imports = [
        _import("google.cloud.storage"),  # declared -> OK
        _import("google.cloud.bigquery", name="google", lineno=2),  # undeclared
    ]
    actual = calculate_undeclared(imports, resolved, [], Settings())
    assert actual == [
        UndeclaredDependency(
            "google.cloud.bigquery",
            [Location("code.py", lineno=2)],
            set(),
        )
    ]


def test_unused__declared_sibling_namespace_is_reported():
    # google-cloud-storage is declared but only google.cloud.bigquery is used.
    resolved = {
        "google-cloud-storage": Package(
            "google-cloud-storage", {"google.cloud.storage"}, IdentityMapping
        ),
    }
    declared = [_dep("google-cloud-storage")]
    imports = [_import("google.cloud.bigquery", name="google")]
    actual = calculate_unused(imports, declared, resolved, Settings())
    assert actual == [
        UnusedDependency("google-cloud-storage", [Location("requirements.txt")])
    ]


def test_no_issues__matching_namespace_package_is_neither_undeclared_nor_unused():
    resolved = {
        "google-cloud-storage": Package(
            "google-cloud-storage", {"google.cloud.storage"}, IdentityMapping
        ),
    }
    declared = [_dep("google-cloud-storage")]
    imports = [_import("google.cloud.storage", name="google")]
    assert calculate_undeclared(imports, resolved, [], Settings()) == []
    assert calculate_unused(imports, declared, resolved, Settings()) == []


# --- Integration: on-disk namespace packages via LocalPackageResolver ---


def _write_namespace_env(site_dir: Path, dists: dict) -> None:
    """Create namespace packages + *.dist-info (with RECORD) under site_dir.

    'dists' maps a distribution name to a list of regular packages it provides
    (as dotted module paths). Each such package is materialized as a PEP 420
    namespace path ending in a regular package (with __init__.py).
    """
    for dist_name, modules in dists.items():
        record_lines = []
        top_levels = set()
        for module in modules:
            parts = module.split(".")
            top_levels.add(parts[0])
            pkg_dir = site_dir.joinpath(*parts)
            pkg_dir.mkdir(parents=True, exist_ok=True)
            init = pkg_dir / "__init__.py"
            init.touch()
            record_lines.append(f"{init.relative_to(site_dir).as_posix()},,")
        dist_info = site_dir / f"{dist_name}-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(f"Name: {dist_name}\nVersion: 1.0\n")
        (dist_info / "top_level.txt").write_text(
            "".join(f"{t}\n" for t in sorted(top_levels))
        )
        record_lines.append(
            f"{(dist_info / 'METADATA').relative_to(site_dir).as_posix()},,"
        )
        (dist_info / "RECORD").write_text("\n".join(record_lines) + "\n")


def test_local_resolver__distinguishes_shared_namespace_distributions(fake_venv):
    _venv_dir, site_dir = fake_venv({})  # a valid, empty venv site-packages dir
    _write_namespace_env(
        site_dir,
        {
            "google-cloud-storage": ["google.cloud.storage"],
            "google-cloud-bigquery": ["google.cloud.bigquery"],
        },
    )

    resolver = LocalPackageResolver({PyEnvSource(site_dir)})
    resolved = resolver.lookup_packages(
        {"google-cloud-storage", "google-cloud-bigquery"}
    )

    assert resolved["google-cloud-storage"].import_names == {"google.cloud.storage"}
    assert resolved["google-cloud-bigquery"].import_names == {"google.cloud.bigquery"}

    # Importing only bigquery, while declaring only storage, must be detected.
    imports = list(
        parse_code(
            dedent("from google.cloud import bigquery\n"),
            source=Location("code.py"),
        )
    )
    only_storage = {"google-cloud-storage": resolved["google-cloud-storage"]}
    undeclared = calculate_undeclared(imports, only_storage, [resolver], Settings())
    assert [u.name for u in undeclared] == ["google.cloud.bigquery"]
    # And the resolver can suggest the right package for the undeclared import.
    assert undeclared[0].candidates == {"google-cloud-bigquery"}
