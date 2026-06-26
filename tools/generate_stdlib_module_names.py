#!/usr/bin/env python3
"""Regenerate ``fawltydeps/_stdlib_module_names.py`` from CPython sources.

FawltyDeps must decide whether an imported top-level name belongs to the Python
standard library (and should therefore *not* be reported as a third-party
dependency). The authoritative answer for a given interpreter is
``sys.stdlib_module_names`` (added in Python 3.10), which CPython itself
generates from its sources via ``Tools/build/generate_stdlib_module_names.py``.

FawltyDeps, however, runs on Python 3.9+ and analyses projects that may target
*any* Python version. We therefore vendor the **union** of
``sys.stdlib_module_names`` across every supported CPython version, so that a
name that is part of the standard library in *any* version is recognised as
such (this mirrors isort's old ``py_version="all"`` behaviour, but using
CPython's authoritative data instead of a docs-scraped list).

This script builds that union by reading, for each CPython release, the
auto-generated ``Python/stdlib_module_names.h`` header straight from a local
CPython git checkout (``../cpython`` by default). Python 3.9 predates both
``sys.stdlib_module_names`` and that header, so for 3.9 we query a real 3.9
interpreter (e.g. ``.nox/tests-3-9/bin/python3.9``) and reproduce CPython's own
generation logic (builtins + ``Lib/`` modules/packages + ``lib-dynload``
extensions), applying the same IGNORE filtering.

Run from the repository root, e.g.::

    python tools/generate_stdlib_module_names.py \
        --cpython ../cpython \
        --py39 .nox/tests-3-9/bin/python3.9

At runtime FawltyDeps additionally unions this vendored set with the *live*
``sys.stdlib_module_names`` of the interpreter it runs under, so newer releases
are picked up automatically even before this file is regenerated.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Release tags in the CPython checkout whose stdlib_module_names.h we read.
# 3.9 has no such header and is handled separately (see collect_py39()).
HEADER_TAGS = ["v3.10.0", "v3.11.0", "v3.12.0", "v3.13.0", "v3.14.0"]
HEADER_PATH = "Python/stdlib_module_names.h"

# Python 2.7 predates sys.stdlib_module_names entirely. We still recognise its
# standard library so that py2/py3-compatibility shims (e.g. the classic
# ``try: import http.server / except ImportError: import BaseHTTPServer``) do
# not get flagged as undeclared third-party dependencies. Python 2 is frozen, so
# this set never changes. We derive it from the v2.7.18 tag's pure-Python
# Lib/ modules plus the C-extension modules declared in Modules/Setup.dist.
PY2_TAG = "v2.7.18"
PY2_SETUP_PATH = "Modules/Setup.dist"
# Frozen core builtins that are not discoverable from the v2.7.18 source tree's
# static config (they are wired in via the interpreter/Makefile, not Setup.dist)
# and are not also part of Python 3's standard library.
PY2_BUILTIN_EXTRAS = {"__builtin__", "thread", "exceptions"}

# Mirrors the IGNORE set in CPython's Tools/build/generate_stdlib_module_names.py:
# internal test/helper modules that are present in Lib/ but are not part of the
# public standard library and must never be listed.
IGNORE = {
    "__init__",
    "__pycache__",
    "site-packages",
    "__hello__",
    "__phello__",
    "__hello_alias__",
    "__phello_alias__",
    "__hello_only__",
    "_ctypes_test",
    "_testbuffer",
    "_testcapi",
    "_testclinic",
    "_testconsole",
    "_testimportmultiple",
    "_testinternalcapi",
    "_testmultiphase",
    "_xxtestfuzz",
    "test",
    "xxlimited",
    "xxlimited_35",
    "xxsubtype",
}

# Output destination, relative to the repository root.
OUTPUT = Path("fawltydeps/_stdlib_module_names.py")

# Script run by a real 3.9 interpreter to reproduce sys.stdlib_module_names.
# Kept faithful to CPython's generate_stdlib_module_names.py for that version.
PY39_PROBE = r"""
import os, sys, json, importlib.machinery
names = set(sys.builtin_module_names)
stdlib_dir = os.path.dirname(os.__file__)
# Pure-Python modules and packages directly under Lib/.
for entry in os.listdir(stdlib_dir):
    path = os.path.join(stdlib_dir, entry)
    if entry.endswith(".py"):
        names.add(entry[:-3])
    elif os.path.isdir(path) and any(
        f.endswith(".py") for f in os.listdir(path)
    ):
        names.add(entry)
# Compiled extension modules in lib-dynload (e.g. 'parser', '_socket', ...).
dynload = os.path.join(stdlib_dir, "lib-dynload")
if os.path.isdir(dynload):
    for entry in os.listdir(dynload):
        for suffix in importlib.machinery.EXTENSION_SUFFIXES:
            if entry.endswith(suffix):
                names.add(entry[: -len(suffix)].split(".", 1)[0])
                break
print(json.dumps(sorted(names)))
"""


def parse_header(text: str) -> set[str]:
    """Extract module names from a stdlib_module_names.h header."""
    return set(re.findall(r'"([^"]+)"', text))


def collect_from_tags(cpython: Path) -> set[str]:
    """Union of stdlib names from each release header in the CPython checkout."""
    names: set[str] = set()
    for tag in HEADER_TAGS:
        out = subprocess.run(
            ["git", "-C", str(cpython), "show", f"{tag}:{HEADER_PATH}"],
            capture_output=True,
            text=True,
            check=True,
        )
        tag_names = parse_header(out.stdout)
        print(f"  {tag}: {len(tag_names)} names", file=sys.stderr)
        names |= tag_names
    # Also include the checked-out (development) version's header, if present.
    head_header = cpython / HEADER_PATH
    if head_header.is_file():
        head_names = parse_header(head_header.read_text())
        print(f"  HEAD: {len(head_names)} names", file=sys.stderr)
        names |= head_names
    return names


def collect_py2(cpython: Path) -> set[str]:
    """Standard-library names for Python 2.7, read from the v2.7.18 tag."""
    names: set[str] = set(PY2_BUILTIN_EXTRAS)
    # Pure-Python modules and top-level packages under Lib/.
    ls = subprocess.run(
        ["git", "-C", str(cpython), "ls-tree", PY2_TAG, "Lib/"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for line in ls.splitlines():
        meta, _, name = line.partition("\t")
        name = name[len("Lib/") :]
        kind = meta.split()[1]
        if kind == "blob" and name.endswith(".py"):
            names.add(name[:-3])
        elif kind == "tree":
            names.add(name)
    # C-extension modules declared (often commented out) in Modules/Setup.dist
    # as "<module_name> <source>.c".
    setup = subprocess.run(
        ["git", "-C", str(cpython), "show", f"{PY2_TAG}:{PY2_SETUP_PATH}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for line in setup.splitlines():
        match = re.match(r"#?\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+\S+\.c", line)
        if match:
            names.add(match.group(1))
    print(f"  py2.7: {len(names)} names", file=sys.stderr)
    return names


def collect_py39(py39: Path) -> set[str]:
    """Reproduce sys.stdlib_module_names for Python 3.9 via a real interpreter."""
    out = subprocess.run(
        [str(py39), "-c", PY39_PROBE],
        capture_output=True,
        text=True,
        check=True,
    )
    names = set(json.loads(out.stdout))
    print(f"  py3.9: {len(names)} names", file=sys.stderr)
    return names


def clean(names: set[str]) -> set[str]:
    """Drop ignored/internal entries and any accidental submodule names."""
    result = set()
    for name in names:
        top = name.split(".", 1)[0]
        if top in IGNORE:
            continue
        if "." in name:  # submodules must never be listed
            continue
        result.add(name)
    return result


def render(names: set[str], *, sources: str) -> str:
    """Render the generated module source for the given set of names."""
    lines = [
        '"""Vendored union of ``sys.stdlib_module_names`` across CPython versions.',
        "",
        "DO NOT EDIT BY HAND. Regenerate with::",
        "",
        "    python tools/generate_stdlib_module_names.py",
        "",
        f"Generated from: {sources}.",
        '"""',
        "",
        # Emitted in `ruff format`'s canonical shape so the generated file does
        # not need a separate formatting pass.
        "STDLIB_MODULE_NAMES = frozenset(",
        "    {",
    ]
    lines += [f'        "{name}",' for name in sorted(names)]
    lines += ["    }", ")", ""]
    return "\n".join(lines)


def main() -> int:
    """Parse arguments, collect the stdlib name union, and write the module."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cpython",
        type=Path,
        default=Path("../cpython"),
        help="Path to a local CPython git checkout (default: ../cpython)",
    )
    parser.add_argument(
        "--py39",
        type=Path,
        default=Path(".nox/tests-3-9/bin/python3.9"),
        help="Path to a Python 3.9 interpreter (default: .nox/tests-3-9/bin/python3.9)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help=f"Where to write the generated module (default: {OUTPUT})",
    )
    args = parser.parse_args()

    print(f"Reading CPython release headers from {args.cpython} ...", file=sys.stderr)
    names = collect_from_tags(args.cpython)

    print(
        f"Reading Python 2.7 stdlib from {args.cpython} ({PY2_TAG}) ...",
        file=sys.stderr,
    )
    names |= collect_py2(args.cpython)

    if args.py39.exists():
        print(f"Probing Python 3.9 at {args.py39} ...", file=sys.stderr)
        names |= collect_py39(args.py39)
    else:
        print(
            f"WARNING: {args.py39} not found; skipping Python 3.9-only modules.",
            file=sys.stderr,
        )

    names = clean(names)
    sources = "CPython 2.7 + 3.9 + " + ", ".join(t.lstrip("v") for t in HEADER_TAGS)
    args.output.write_text(render(names, sources=sources))
    print(f"Wrote {len(names)} module names to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
