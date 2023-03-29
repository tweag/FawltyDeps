"""Declare command line options.

Part of the options are strictly related to `Settings` object
and part is for general purpose.
"""

import argparse

from fawltydeps.settings import setup_cmdline_parser
from fawltydeps.utils import version


def build_parser(description: str = "") -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser, option_group = setup_cmdline_parser(description=description)
    option_group.add_argument(
        "--generate-toml-config",
        action="store_true",
        default=False,
        help="Print a TOML config section with the current settings, and exit",
    )
    option_group.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"FawltyDeps v{version()}",
        help="Print the version number of FawltyDeps",
    )
    # setup_cmdline_parser() removes the automatic `--help` option so that we
    # can control exactly where it's added. Here we add it back:
    option_group.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit",
    )
    return parser
