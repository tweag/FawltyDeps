"""Find undeclared and/or unused 3rd-party dependencies in your Python project.

* Supported files for Python code containing third-party imports:
  * Python scripts with filenames that end in `.py`
  * Jupyter notebooks with filenames that end in `.ipynb`

* Supported files/formats for dependency declarations:
  * `*requirements*.txt` and `*requirements*.in`
  * `pyproject.toml` (following PEP 621 or Poetry conventions)
  * `setup.py` (only limited support for simple files with a single `setup()`
    call and no computation involved for setting the `install_requires` and
    `extras_require` arguments)
  * `setup.cfg`
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from enum import Enum, auto
from operator import attrgetter
from pathlib import Path
from typing import Iterable, List, Optional, Set, TextIO, no_type_check

from pydantic.json import pydantic_encoder  # pylint: disable=no-name-in-module

from fawltydeps import extract_imports
from fawltydeps.check import compare_imports_to_dependencies
from fawltydeps.extract_declared_dependencies import extract_declared_dependencies
from fawltydeps.types import (
    ArgParseError,
    DeclaredDependency,
    ParsedImport,
    PathOrSpecial,
    UndeclaredDependency,
    UnusedDependency,
)
from fawltydeps.utils import hide_dataclass_fields

if sys.version_info >= (3, 8):
    import importlib.metadata as importlib_metadata
else:
    import importlib_metadata


logger = logging.getLogger(__name__)

VERBOSE_PROMPT = "For a more verbose report re-run with the `-v` option."


class Action(Enum):
    """Actions available to the command-line interface."""

    LIST_IMPORTS = auto()
    LIST_DEPS = auto()
    REPORT_UNDECLARED = auto()
    REPORT_UNUSED = auto()


@no_type_check
def version() -> str:
    """Returns the version of fawltydeps."""

    # This function is extracted to allow annotation with `@no_type_check`.
    # Using `#type: ignore` on the line below leads to an
    # "unused type ignore comment" MyPy error in python's version 3.8 and
    # higher.
    return str(importlib_metadata.version("fawltydeps"))


@dataclass
class Analysis:
    """Result from FawltyDeps analysis, to be presented to the user."""

    request: Set[Action]
    imports: Optional[List[ParsedImport]] = None
    declared_deps: Optional[List[DeclaredDependency]] = None
    undeclared_deps: Optional[List[UndeclaredDependency]] = None
    unused_deps: Optional[List[UnusedDependency]] = None

    def is_enabled(self, *args: Action) -> bool:
        """Return True if any of the given actions are in self.request."""
        return len(self.request.intersection(args)) > 0

    @classmethod
    def create(
        cls,
        request: Set[Action],
        code: PathOrSpecial,
        deps: Path,
        ignored_unused: Iterable[str] = (),
        ignored_undeclared: Iterable[str] = (),
    ) -> "Analysis":
        """Perform the requested actions of FawltyDeps core logic.

        This is a high-level interface to the services offered by FawltyDeps.
        Although the main caller is the command-line interface defined below,
        this can also be called from other Python contexts without having to go
        via the command-line.
        """
        ret = cls(request)
        if ret.is_enabled(
            Action.LIST_IMPORTS, Action.REPORT_UNDECLARED, Action.REPORT_UNUSED
        ):
            ret.imports = list(extract_imports.parse_any_arg(code))

        if ret.is_enabled(
            Action.LIST_DEPS, Action.REPORT_UNDECLARED, Action.REPORT_UNUSED
        ):
            ret.declared_deps = list(extract_declared_dependencies(deps))

        if ret.is_enabled(Action.REPORT_UNDECLARED, Action.REPORT_UNUSED):
            assert ret.imports is not None  # convince Mypy that these cannot
            assert ret.declared_deps is not None  # be None at this time.
            ret.undeclared_deps, ret.unused_deps = compare_imports_to_dependencies(
                imports=ret.imports,
                dependencies=ret.declared_deps,
                ignored_unused=ignored_unused,
                ignored_undeclared=ignored_undeclared,
            )

        return ret

    def __post_init__(self) -> None:
        """Do init-time magic to hide .request from JSON representation."""
        hide_dataclass_fields(self, "request")

    def print_json(self, out: TextIO) -> None:
        """Print the JSON representation of this analysis to 'out'."""
        json.dump(self, out, indent=2, default=pydantic_encoder)

    def print_human_readable(self, out: TextIO, details: bool = True) -> None:
        """Print a human-readable rendering of this analysis to 'out'."""
        if self.is_enabled(Action.LIST_IMPORTS):
            assert self.imports is not None  # sanity-check / convince Mypy
            if details:
                # Sort imports by source, then by name
                for imp in sorted(self.imports, key=attrgetter("source", "name")):
                    print(f"{imp.source}: {imp.name}", file=out)
            else:
                unique_imports = {i.name for i in self.imports}
                print("\n".join(sorted(unique_imports)), file=out)

        if self.is_enabled(Action.LIST_DEPS):
            assert self.declared_deps is not None  # sanity-check / convince Mypy
            if details:
                # Sort dependencies by location, then by name
                for dep in sorted(self.declared_deps, key=attrgetter("source", "name")):
                    print(f"{dep.source}: {dep.name}", file=out)
            else:
                unique_dependencies = {i.name for i in self.declared_deps}
                print("\n".join(sorted(unique_dependencies)), file=out)

        if self.is_enabled(Action.REPORT_UNDECLARED) and self.undeclared_deps:
            print("These imports appear to be undeclared dependencies:", file=out)
            for undeclared in self.undeclared_deps:
                print(f"- {undeclared.render(details)}", file=out)

        if self.is_enabled(Action.REPORT_UNUSED) and self.unused_deps:
            print(
                "These dependencies appear to be unused (i.e. not imported):", file=out
            )
            for unused in self.unused_deps:
                print(f"- {unused.render(details)}", file=out)


def parse_path_or_stdin(arg: str) -> PathOrSpecial:
    """Convert --code argument into Path or "<stdin>"."""
    if arg == "-":
        return "<stdin>"
    return Path(arg)


def main() -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        add_help=False,
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    select_action = parser.add_argument_group(
        title="Actions"
    ).add_mutually_exclusive_group()
    select_action.add_argument(
        "--check",
        dest="actions",
        action="store_const",
        const={Action.REPORT_UNDECLARED, Action.REPORT_UNUSED},
        help="Report both undeclared and unused dependencies",
    )
    select_action.add_argument(
        "--check-undeclared",
        dest="actions",
        action="store_const",
        const={Action.REPORT_UNDECLARED},
        help="Report only unudeclared dependencies",
    )
    select_action.add_argument(
        "--check-unused",
        dest="actions",
        action="store_const",
        const={Action.REPORT_UNUSED},
        help="Report only unused dependencies",
    )
    select_action.add_argument(
        "--list-imports",
        dest="actions",
        action="store_const",
        const={Action.LIST_IMPORTS},
        help="List third-party imports extracted from code and exit",
    )
    select_action.add_argument(
        "--list-deps",
        dest="actions",
        action="store_const",
        const={Action.LIST_DEPS},
        help="List declared dependencies and exit",
    )

    options = parser.add_argument_group(title="Options")
    options.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"FawltyDeps v{version()}",
        help=("Print the version number of FawltyDeps"),
    )
    options.add_argument(
        "--code",
        type=parse_path_or_stdin,
        default=Path("."),
        help=(
            "Code to parse for import statements (file or directory, use '-' "
            "to read code from stdin; defaults to the current directory)"
        ),
    )
    options.add_argument(
        "--deps",
        type=Path,
        default=Path("."),
        help=(
            "Where to find dependency declarations (file or directory, defaults"
            " to looking for supported files in the current directory)"
        ),
    )
    options.add_argument(
        "--json",
        action="store_true",
        help="Generate JSON output instead of a human-readable report",
    )
    options.add_argument(
        "--ignore-unused",
        nargs="+",
        default=[],
        help=(
            "Dependencies to ignore when looking for unused"
            " dependencies, e.g. --ignore-unused pylint black"
        ),
    )
    options.add_argument(
        "--ignore-undeclared",
        nargs="+",
        default=[],
        help=(
            "Imports to ignore when looking for undeclared"
            " dependencies, e.g. --ignore-undeclared isort pkg_resources"
        ),
    )
    options.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help=(
            "Increase log level (WARNING by default, -v: INFO, -vv: DEBUG)"
            " and verbosity of the output (without location details by default,"
            " -v, -vv: with location details)"
        ),
    )
    options.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
        help="Decrease log level (WARNING by default, -q: ERROR, -qq: FATAL)",
    )
    options.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="Show this help message and exit",
    )

    args = parser.parse_args()

    verbosity = args.verbose - args.quiet
    verbose_report = verbosity > 0
    logging.basicConfig(level=logging.WARNING - 10 * verbosity)

    actions = args.actions or {Action.REPORT_UNDECLARED, Action.REPORT_UNUSED}

    try:
        analysis = Analysis.create(
            actions,
            args.code,
            args.deps,
            args.ignore_unused,
            args.ignore_undeclared,
        )
    except ArgParseError as exc:
        return parser.error(exc.msg)  # exit code 2

    if args.json:
        analysis.print_json(sys.stdout)
    else:
        analysis.print_human_readable(sys.stdout, details=verbose_report)
        if not verbose_report:
            print(f"\n{VERBOSE_PROMPT}\n")

    # Exit codes:
    # 0 - success, no problems found
    # 1 - an exception propagates (this should not happen)
    # 2 - command-line parsing error (see above)
    # 3 - undeclared dependencies found
    # 4 - unused dependencies found
    if analysis.is_enabled(Action.REPORT_UNDECLARED) and analysis.undeclared_deps:
        return 3
    if analysis.is_enabled(Action.REPORT_UNUSED) and analysis.unused_deps:
        return 4
    return 0
