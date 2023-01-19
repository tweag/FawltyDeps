"""Find undeclared 3rd-party dependencies in your Python project."""

import argparse
import logging
from dataclasses import dataclass
from enum import Enum, auto
from operator import itemgetter
from pathlib import Path
from typing import Optional, Set

from fawltydeps import extract_imports
from fawltydeps.check import compare_imports_to_dependencies
from fawltydeps.extract_dependencies import extract_dependencies
from fawltydeps.types import DeclaredDependency, ParsedImport

logger = logging.getLogger(__name__)


class Action(Enum):
    """Actions available to the command-line interface."""

    LIST_IMPORTS = auto()
    LIST_DEPS = auto()
    REPORT_UNDECLARED = auto()
    REPORT_UNUSED = auto()


@dataclass
class Report:
    """Result from perform_actions(), to be presented to the user."""

    imports: Optional[Set[ParsedImport]] = None
    declared_deps: Optional[Set[DeclaredDependency]] = None
    undeclared_deps: Optional[Set[str]] = None
    unused_deps: Optional[Set[str]] = None


def perform_actions(actions: Set[Action], code: Path, deps: Path) -> Report:
    """Perform the requested actions of FawltyDeps core logic.

    This is a high-level interface to the services offered by FawltyDeps.
    Although the main caller is the command-line interface defined below, this
    can also be called from other Python contexts without having to go via the
    command-line.
    """

    def is_enabled(*args: Action) -> bool:
        return len(actions.intersection(args)) > 0

    report = Report()
    if is_enabled(Action.LIST_IMPORTS, Action.REPORT_UNDECLARED, Action.REPORT_UNUSED):
        report.imports = set(extract_imports.parse_any_arg(code))

    if is_enabled(Action.LIST_DEPS, Action.REPORT_UNDECLARED, Action.REPORT_UNUSED):
        report.declared_deps = set(extract_dependencies(deps))

    if is_enabled(Action.REPORT_UNDECLARED, Action.REPORT_UNUSED):
        # TODO: Better handling of location information
        assert report.imports is not None
        assert report.declared_deps is not None
        comparison = compare_imports_to_dependencies(
            {i.name for i in report.imports},
            {name for name, _ in report.declared_deps},
        )
        report.undeclared_deps = comparison.undeclared
        report.unused_deps = comparison.unused

    return report


def print_human_readable_report(actions: Set[Action], report: Report) -> None:
    """Print a human-readable rendering of the given report to stdout."""

    def is_enabled(*args: Action) -> bool:
        return len(actions.intersection(args)) > 0

    def relpath(path: Optional[Path]) -> Path:
        """Make 'path' relative to current directory, if possible"""
        if path is None:
            return Path("<unknown>")
        try:
            return path.relative_to(Path.cwd())
        except ValueError:
            return path

    if is_enabled(Action.LIST_IMPORTS):
        assert report.imports is not None
        # Sort imports by location, then by name
        for name, location in sorted(report.imports, key=itemgetter(1, 0)):
            print(f"{name}: {relpath(location)}")

    if is_enabled(Action.LIST_DEPS):
        assert report.declared_deps is not None
        # Sort dependencies by location, then by name
        for name, location in sorted(report.declared_deps, key=itemgetter(1, 0)):
            print(f"{name}: {relpath(location)}")

    if is_enabled(Action.REPORT_UNDECLARED) and report.undeclared_deps:
        print("These imports are not declared as dependencies:")
        for name in sorted(report.undeclared_deps):
            print(f"- {name}")

    if is_enabled(Action.REPORT_UNUSED) and report.unused_deps:
        print("These dependencies are not imported in your code:")
        for name in sorted(report.unused_deps):
            print(f"- {name}")


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
        type=Path,
        default=Path.cwd(),
        help=(
            "Code to parse for import statements (file or directory, use '-' "
            "to read code from stdin; defaults to the current directory)"
        ),
    )
    parser.add_argument(
        "--deps",
        type=Path,
        default=Path.cwd(),
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

    logging.basicConfig(
        level=logging.WARNING + 10 * (args.quiet - args.verbose),
    )

    actions = args.actions or {Action.REPORT_UNDECLARED, Action.REPORT_UNUSED}

    try:
        report = perform_actions(actions, args.code, args.deps)
    except extract_imports.ParseError as e:
        return parser.error(e.msg)  # exit code 2

    print_human_readable_report(actions, report)

    # Exit codes:
    # 0 - success, no problems found
    # 1 - an exception propagates (this should not happen)
    # 2 - command-line parsing error (see above)
    # 3 - undeclared dependencies found
    # 4 - unused dependencies found
    if report.undeclared_deps and Action.REPORT_UNDECLARED in actions:
        return 3
    if report.unused_deps and Action.REPORT_UNUSED in actions:
        return 4
    return 0
