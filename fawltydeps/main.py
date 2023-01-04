"""Find undeclared 3rd-party dependencies in your Python project."""

import argparse
import logging
from enum import Enum, auto
from operator import itemgetter
from pathlib import Path
from typing import Set

from fawltydeps import extract_imports
from fawltydeps.extract_dependencies import extract_dependencies

logger = logging.getLogger(__name__)


class Action(Enum):
    """Actions available to the command-line interface."""

    LIST_IMPORTS = auto()
    LIST_DEPS = auto()


def perform_actions(actions: Set[Action], code: Path, deps: Path) -> int:
    if actions & {Action.LIST_IMPORTS}:
        extracted_imports = set(extract_imports.parse_any_arg(code))
        for name in sorted(extracted_imports):
            # TODO: Add location information to extracted imports
            print(name)

    if actions & {Action.LIST_DEPS}:
        extracted_deps = set(extract_dependencies(deps))
        # Sort dependencies by location, then by name
        for name, location in sorted(extracted_deps, key=itemgetter(1, 0)):
            print(f"{name}: {location}")

    return 0


def main() -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)

    select_action = parser.add_mutually_exclusive_group()
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

    if args.actions is None:  # Provide default action
        args.actions = {Action.LIST_IMPORTS}

    try:
        return perform_actions(args.actions, args.code, args.deps)
    except extract_imports.ParseError as e:
        return parser.error(e.msg)
