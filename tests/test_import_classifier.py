"""Tests for the native (isort-free) import classifier."""

import sys

import pytest

from fawltydeps.import_classifier import (
    LocalContext,
    is_first_party_module,
    is_stdlib_module,
    make_local_context,
    stdlib_module_names,
)


@pytest.mark.parametrize(
    "name",
    [
        "sys",
        "os",
        "os.path",  # submodule of a stdlib package
        "pathlib",
        "__future__",
        "_ast",  # underscore-prefixed stdlib module (isort's lists dropped these)
        "concurrent",  # stdlib package
        "tomllib",  # added in Python 3.11
        "asyncio",
    ],
)
def test_is_stdlib_module__recognises_standard_library(name):
    assert is_stdlib_module(name)


@pytest.mark.parametrize(
    "name",
    [
        "parser",  # removed in Python 3.10
        "formatter",  # removed in Python 3.10
        "symbol",  # removed in Python 3.10
        "asynchat",  # removed in Python 3.12
    ],
)
def test_is_stdlib_module__recognises_recently_removed_modules(name):
    # FawltyDeps stays version-agnostic: a module that was standard-library in
    # *any* supported Python version is recognised as such.
    assert is_stdlib_module(name)


@pytest.mark.parametrize(
    "name",
    [
        "BaseHTTPServer",  # Python 2 -> http.server
        "SimpleHTTPServer",
        "StringIO",
        "cStringIO",
        "cPickle",
        "Queue",  # Python 2 -> queue
        "urllib2",
        "__builtin__",
    ],
)
def test_is_stdlib_module__recognises_python2_modules(name):
    # py2/py3-compatibility shims (try/except ImportError) should not be flagged.
    assert is_stdlib_module(name)


@pytest.mark.parametrize("name", ["numpy", "requests", "pandas", "fawltydeps"])
def test_is_stdlib_module__rejects_third_party(name):
    assert not is_stdlib_module(name)


def test_stdlib_module_names__merges_live_interpreter():
    names = stdlib_module_names()
    live = getattr(sys, "stdlib_module_names", frozenset())
    assert live <= names


def test_is_first_party_module__source_file(tmp_path):
    (tmp_path / "my_module.py").write_text("x = 1\n")
    assert is_first_party_module("my_module", [tmp_path])
    assert not is_first_party_module("other_module", [tmp_path])


def test_is_first_party_module__regular_package(tmp_path):
    pkg = tmp_path / "my_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    assert is_first_party_module("my_pkg", [tmp_path])
    assert is_first_party_module("my_pkg.submodule", [tmp_path])


def test_is_first_party_module__namespace_package(tmp_path):
    # A directory without __init__.py is still importable as a namespace package.
    pkg = tmp_path / "ns_pkg"
    pkg.mkdir()
    (pkg / "thing.py").write_text("")
    assert is_first_party_module("ns_pkg", [tmp_path])
    assert is_first_party_module("ns_pkg.thing", [tmp_path])


def test_is_first_party_module__src_path_is_a_regular_package(tmp_path):
    # Pointing a source dir *at* a regular package (e.g. `--code my_app`) must
    # still treat `import my_app` as first-party, because the package is
    # importable from its parent -- exactly as CPython resolves it with the
    # parent on sys.path. (We add that parent as an import root.)
    pkg = tmp_path / "my_app"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    assert is_first_party_module("my_app", [pkg])
    assert is_first_party_module("my_app.submodule", [pkg])
    # ...and of course also when the parent itself is the source dir.
    assert is_first_party_module("my_app", [tmp_path])


def test_is_first_party_module__non_package_dir_named_like_import_is_not(tmp_path):
    # The bug we are fixing: a source dir that merely *shares its name* with a
    # third-party package -- but is not an importable package (no __init__.py) --
    # must NOT shadow that dependency. CPython would not resolve `import numpy`
    # from a sys.path entry that is itself the (non-package) `numpy` directory.
    # This is the isort behaviour (`_src_path_is_module`) we deliberately dropped.
    numpy_dir = tmp_path / "numpy"
    numpy_dir.mkdir()
    (numpy_dir / "data.txt").write_text("not a python package")
    assert not is_first_party_module("numpy", [numpy_dir])


def test_local_context__third_party_unless_stdlib_or_first_party(tmp_path):
    (tmp_path / "local_mod.py").write_text("")
    ctx = make_local_context(tmp_path)
    assert ctx.is_third_party("requests")
    assert not ctx.is_third_party("os")  # stdlib
    assert not ctx.is_third_party("local_mod")  # first-party


def test_local_context__empty_has_no_first_party():
    ctx = LocalContext()
    assert ctx.is_third_party("requests")
    assert not ctx.is_third_party("sys")
