"""Find undeclared and/or unused 3rd-party dependencies in your Python project."""

import argparse
import logging
import sys
from dataclasses import dataclass
from enum import Enum, auto
from operator import attrgetter
from pathlib import Path
from typing import List, Optional, Set, TextIO

from fawltydeps import extract_imports
from fawltydeps.check import compare_imports_to_dependencies
from fawltydeps.extract_dependencies import extract_dependencies
from fawltydeps.types import (
    ArgParseError,
    DeclaredDependency,
    ParsedImport,
    PathOrSpecial,
    UndeclaredDependency,
    UnusedDependency,
)

logger = logging.getLogger(__name__)


class Action(Enum):
    """Actions available to the command-line interface."""

    LIST_IMPORTS = auto()
    LIST_DEPS = auto()
    REPORT_UNDECLARED = auto()
    REPORT_UNUSED = auto()


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
        cls, request: Set[Action], code: PathOrSpecial, deps: Path
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
            ret.declared_deps = list(extract_dependencies(deps))

        if ret.is_enabled(Action.REPORT_UNDECLARED, Action.REPORT_UNUSED):
            assert ret.imports is not None  # convince Mypy that these cannot
            assert ret.declared_deps is not None  # be None at this time.
            ret.undeclared_deps, ret.unused_deps = compare_imports_to_dependencies(
                imports=ret.imports, dependencies=ret.declared_deps
            )

        return ret

    def print_human_readable(self, out: TextIO, details: bool = True) -> None:
        """Print a human-readable rendering of the given report to stdout."""
        if self.is_enabled(Action.LIST_IMPORTS):
            assert self.imports is not None  # sanity-check / convince Mypy
            # Sort imports by source, then by name
            for imp in sorted(self.imports, key=attrgetter("source", "name")):
                print(f"{imp.source}: {imp.name}", file=out)

        if self.is_enabled(Action.LIST_DEPS):
            assert self.declared_deps is not None  # sanity-check / convince Mypy
            # Sort dependencies by location, then by name
            for dep in sorted(self.declared_deps, key=attrgetter("source", "name")):
                print(f"{dep.source}: {dep.name}", file=out)

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
    parser = argparse.ArgumentParser(description=__doc__)

    select_action = parser.add_mutually_exclusive_group()
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
        help="List imports extracted from code and exit",
    )
    select_action.add_argument(
        "--list-deps",
        dest="actions",
        action="store_const",
        const={Action.LIST_DEPS},
        help="List declared dependencies and exit",
    )

    parser.add_argument(
        "--code",
        type=parse_path_or_stdin,
        default=Path("."),
        help=(
            "Code to parse for import statements (file or directory, use '-' "
            "to read code from stdin; defaults to the current directory)"
        ),
    )
    parser.add_argument(
        "--deps",
        type=Path,
        default=Path("."),
        help=(
            "Where to find dependency declarations (file or directory, defaults"
            " to looking for requirements.txt/.in/setup.py/pyproject.toml in "
            "the current directory)"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase log level (WARNING by default, -v: INFO, -vv: DEBUG)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
        help="Decrease log level (WARNING by default, -q: ERROR, -qq: FATAL)",
    )

    args = parser.parse_args()

    verbosity = args.verbose - args.quiet
    logging.basicConfig(level=logging.WARNING - 10 * verbosity)

    actions = args.actions or {Action.REPORT_UNDECLARED, Action.REPORT_UNUSED}

    try:
        analysis = Analysis.create(actions, args.code, args.deps)
    except ArgParseError as exc:
        return parser.error(exc.msg)  # exit code 2

    analysis.print_human_readable(sys.stdout, details=verbosity >= 0)

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
