"""Find undeclared 3rd-party dependencies in your Python project."""

import argparse
import logging
from pathlib import Path

from fawltydeps import extract_imports

logger = logging.getLogger(__name__)


def main() -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
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

    try:
        extracted_imports = set(extract_imports.parse_any_arg(args.code))
    except extract_imports.ParseError as e:
        parser.error(e.msg)

    # TODO: Extract declared dependencies
    # TODO: Pass imports and dependencies to comparator.
    # Until then:
    for imp in sorted(extracted_imports):
        print(imp)

    return 0
