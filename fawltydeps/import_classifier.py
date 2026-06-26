"""Classify a top-level import name as standard-library, first- or third-party.

This reimplements the slice of ``isort.place_module()`` that FawltyDeps relied
on, but stays close to CPython's *own* import machinery instead of isort's
docs-scraped tables:

* **Standard library** membership comes from ``sys.stdlib_module_names`` -- the
  authoritative set CPython generates from its sources
  (``../cpython/Tools/build/generate_stdlib_module_names.py`` ->
  ``../cpython/Python/stdlib_module_names.h``, exposed via
  ``../cpython/Objects/moduleobject.c``). Because FawltyDeps runs on Python
  3.9+ and analyses projects targeting *any* Python version, we use the vendored
  union of that set across CPython releases (see
  ``tools/generate_stdlib_module_names.py``) merged with the live interpreter's
  own ``sys.stdlib_module_names``.

* **First-party** resolution mirrors the path-based import machinery in
  ``../cpython/Lib/importlib/_bootstrap_external.py``:

  - ``PathFinder._get_spec`` iterates the ``sys.path`` entries
    (``for entry in path``) and asks each entry's finder to locate the module.
    We model the ``sys.path`` entries with the configured source directories
    (``src_paths``) and iterate them the same way.
  - ``FileFinder.find_spec`` then resolves a single name *inside* one directory.
    For ``tail_module`` it accepts, in order: a regular package
    (``<dir>/<name>/__init__<suffix>`` is a file), a namespace package
    (``<dir>/<name>`` is a directory with no ``__init__``), or a module file
    (``<dir>/<name><suffix>``). The recognised suffixes come from
    ``_get_supported_file_loaders`` -> ``SOURCE_SUFFIXES`` (``.py``),
    ``BYTECODE_SUFFIXES`` (``.pyc``) and ``EXTENSION_SUFFIXES``
    (``_imp.extension_suffixes()``); see :func:`_is_module` / :func:`_is_package`
    for which of these FawltyDeps checks and why.

  Like the import machinery, only the *top-level* component of a dotted name is
  resolved against ``src_paths`` (``PathFinder``/``FileFinder`` only ever look up
  one name at a time; deeper components are searched relative to the parent
  package's ``__path__``, which for a first-party root is irrelevant to us).

Anything that is neither standard-library nor first-party is treated as a
third-party import, i.e. a dependency that FawltyDeps should account for.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache, lru_cache
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path

from fawltydeps._stdlib_module_names import STDLIB_MODULE_NAMES


@lru_cache(maxsize=1)
def stdlib_module_names() -> frozenset[str]:
    """Return all top-level standard-library module names.

    This is the vendored union of ``sys.stdlib_module_names`` across CPython
    releases, merged with the running interpreter's own
    ``sys.stdlib_module_names`` (available since Python 3.10) so that modules
    added by a newer interpreter are recognised even before the vendored list
    is regenerated.
    """
    live: frozenset[str] = frozenset(getattr(sys, "stdlib_module_names", ()))
    return STDLIB_MODULE_NAMES | live


def is_stdlib_module(name: str) -> bool:
    """Return whether the given import name belongs to the standard library."""
    return name.split(".", 1)[0] in stdlib_module_names()


def _exists_case_sensitive(path: Path) -> bool:
    """Return whether ``path`` exists, matching case even on case-insensitive FS.

    Mirrors ``isort.utils.exists_case_sensitive``: on Windows and macOS the
    filesystem is typically case-insensitive, but CPython's import machinery
    only imports a module when the case of the file on disk matches.
    """
    if not path.exists():
        return False
    # Assign to a local first so that mypy does not treat the macOS/Windows
    # branch as statically unreachable on other platforms (warn_unreachable).
    platform = sys.platform
    if platform.startswith("win") or platform == "darwin":  # pragma: no cover
        return any(path.name == entry.name for entry in path.parent.iterdir())
    return True


def _is_module(path: Path) -> bool:
    """Return whether ``path`` (without suffix) names an importable module.

    This is the module/regular-package half of ``FileFinder.find_spec``
    (``_bootstrap_external.py``). ``path`` is ``<src_dir>/<name>``; it is
    importable as:

    - a regular package -- ``<path>/__init__.py`` exists. ``find_spec`` checks
      ``__init__<suffix>`` for every loader suffix; we only check ``.py``, since
      an ``__init__`` that exists *only* as ``.pyc``/extension with no ``.py`` is
      not something a source analyser can read anyway.
    - a source module -- ``<path>.py`` exists (CPython ``SOURCE_SUFFIXES``).
    - a compiled extension module -- ``<path><ext>`` exists for some ``ext`` in
      ``importlib.machinery.EXTENSION_SUFFIXES`` (CPython ``EXTENSION_SUFFIXES``).

    We deliberately do *not* check ``BYTECODE_SUFFIXES`` (``.pyc``): FawltyDeps
    analyses source trees, and a first-party module shipped only as ``.pyc`` is
    both vanishingly rare and unanalysable. This is the one loader suffix from
    ``_get_supported_file_loaders`` we drop; isort's resolver dropped it too.
    """
    if _exists_case_sensitive(path.with_name(path.name + ".py")):
        return True
    if any(
        _exists_case_sensitive(path.with_name(path.name + ext))
        for ext in EXTENSION_SUFFIXES
    ):
        return True
    return _exists_case_sensitive(path / "__init__.py")


def _is_package(path: Path) -> bool:
    """Return whether ``path`` is an importable namespace-package directory.

    Corresponds to the namespace branch of ``FileFinder.find_spec``
    (``is_namespace = _path_isdir(base_path)``): a directory with no ``__init__``
    is still importable as a namespace-package portion (PEP 420). A regular
    package directory (with ``__init__``) is already covered by :func:`_is_module`.
    """
    return _exists_case_sensitive(path) and path.is_dir()


@cache
def _import_roots(src_paths: tuple[Path, ...]) -> tuple[Path, ...]:
    """Expand source directories to the import roots CPython would search.

    Each configured source directory stands in for a ``sys.path`` entry. But if
    a source directory is *itself* a regular package -- or sits inside a chain of
    them (each level has ``__init__.py``) -- then the directory from which that
    package is importable is an ancestor: the first one **without**
    ``__init__.py``. CPython only finds a top-level package from that ancestor
    (it must be on ``sys.path``), so we add those ancestors as additional search
    roots. This is what makes ``fawltydeps --code mypkg`` (which sets the base
    dir to ``mypkg`` itself) still resolve ``import mypkg`` -- exactly as Python
    does with ``mypkg``'s parent on ``sys.path``.

    Crucially this keys off ``__init__.py`` (a *regular* package). A directory
    that merely shares a name with a third-party package, but is not an
    importable package, therefore never shadows that dependency. Matching a
    source directory against its own *name* -- regardless of whether it is a
    package -- was the isort behaviour (``_src_path_is_module``) FawltyDeps used
    to inherit; it silently hid any dependency whose name collided with a project
    directory (e.g. a repo checked out into a directory called ``numpy``), and is
    deliberately dropped here.
    """
    roots = set(src_paths)
    for src_path in src_paths:
        node = src_path
        while (node / "__init__.py").exists():
            parent = node.parent
            if parent == node:  # reached the filesystem root; stop
                break
            node = parent
            roots.add(node)
    return tuple(roots)


@cache
def _is_first_party_root(src_paths: tuple[Path, ...], root_module_name: str) -> bool:
    """Resolve whether ``root_module_name`` is first-party, caching the result.

    This is the ``src_paths`` analogue of ``PathFinder._get_spec``
    (``_bootstrap_external.py``): iterate the import roots (our stand-in for
    ``sys.path`` entries; see :func:`_import_roots`) and, for each, try to locate
    ``root_module_name`` *inside* it via ``FileFinder.find_spec`` semantics
    (:func:`_is_module` / :func:`_is_package`). The first root that resolves it
    wins.

    Results are memoised on ``(src_paths, root_module_name)`` -- mirroring the
    ``@lru_cache`` that ``isort.place.module_with_reason`` put on its placement
    decisions -- so that a module imported across many files is only resolved
    against the filesystem once.
    """
    for src_path in _import_roots(src_paths):
        module_path = (src_path / root_module_name).resolve()
        if _is_module(module_path) or _is_package(module_path):
            return True
    return False


def is_first_party_module(name: str, src_paths: Iterable[Path]) -> bool:
    """Return whether ``name`` resolves to a local module under ``src_paths``.

    Only the top-level component of ``name`` is resolved, matching how Python's
    import machinery locates the root of a dotted import before descending into
    submodules.
    """
    return _is_first_party_root(tuple(src_paths), name.split(".", 1)[0])


@dataclass(frozen=True)
class LocalContext:
    """Knowledge needed to classify imports relative to a project.

    ``src_paths`` are the source directories under which first-party modules are
    found. This replaces the ``isort.Config`` object FawltyDeps used to thread
    through the import-parsing code.
    """

    src_paths: tuple[Path, ...] = ()

    def is_third_party(self, name: str) -> bool:
        """Return whether ``name`` is a third-party (dependency) import.

        A name is third-party unless it is part of the standard library or
        resolves to a first-party module under one of ``src_paths``.

        CPython resolves imports by walking ``sys.meta_path``
        (``BuiltinImporter`` -> ``FrozenImporter`` -> ``PathFinder`` over
        ``sys.path``; see ``../cpython/Lib/importlib/_bootstrap.py``), where the
        standard library and first-party code are interleaved on ``sys.path``
        and a first-party module can *shadow* a stdlib one. We do not need that
        precise ordering: FawltyDeps only asks "is this a third-party
        dependency?", and stdlib and first-party both answer "no", so the order
        in which we rule them out does not change the result.
        """
        if is_stdlib_module(name):
            return False
        return not is_first_party_module(name, self.src_paths)


def make_local_context(path: Path, src_paths: tuple[Path, ...] = ()) -> LocalContext:
    """Build a :class:`LocalContext` rooted at ``path`` plus extra ``src_paths``.

    First-party imports are resolved relative to ``path`` and each of the given
    ``src_paths``.
    """
    return LocalContext(src_paths=(path, *src_paths))


#: Fallback context used when no project source directories are known: resolve
#: first-party imports relative to the current working directory only.
FALLBACK_CONTEXT = make_local_context(Path())
