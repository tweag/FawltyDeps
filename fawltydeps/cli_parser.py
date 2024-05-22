"""Declare command line options.

Part of the options are strictly related to `Settings` object
and part is for general purpose.
"""

import argparse
from pathlib import Path
from typing import Any, Optional, Sequence

from fawltydeps.settings import (
    Action,
    ParserChoice,
    parse_path_or_stdin,
    read_parser_choice,
)
from fawltydeps.utils import version


class ArgparseUnionAction(argparse.Action):
    """Action to take the union of given arguments/values for one CLI option."""

    def __call__(  # type: ignore[misc, override]
        self,
        _parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Sequence[Any],
        _option_string: Optional[str] = None,
    ) -> None:
        """Compute the union of 'values' and any previously given values'."""
        items = getattr(namespace, self.dest, [])
        setattr(namespace, self.dest, set(items) | set(values))


def populate_parser_actions(parser: argparse._ActionsContainer) -> None:
    """Add the Actions-related arguments to the command-line parser.

    These are mutually exclusive options that each will set the .actions
    member to a set of 'Action's. If not given, the .actions member will
    remain unset, to allow the underlying default to come through.
    """
    parser.add_argument(
        "--check",
        dest="actions",
        action="store_const",
        const={Action.REPORT_UNDECLARED, Action.REPORT_UNUSED},
        help="Report both undeclared and unused dependencies (default)",
    )
    parser.add_argument(
        "--check-undeclared",
        dest="actions",
        action="store_const",
        const={Action.REPORT_UNDECLARED},
        help="Report only undeclared dependencies",
    )
    parser.add_argument(
        "--check-unused",
        dest="actions",
        action="store_const",
        const={Action.REPORT_UNUSED},
        help="Report only unused dependencies",
    )
    parser.add_argument(
        "--list-sources",
        dest="actions",
        action="store_const",
        const={Action.LIST_SOURCES},
        help=(
            "List input paths used to extract imports, declared dependencies "
            "and find installed packages"
        ),
    )
    parser.add_argument(
        "--list-imports",
        dest="actions",
        action="store_const",
        const={Action.LIST_IMPORTS},
        help="List third-party imports extracted from code",
    )
    parser.add_argument(
        "--list-deps",
        dest="actions",
        action="store_const",
        const={Action.LIST_DEPS},
        help="List declared dependencies",
    )


def populate_output_formats(parser: argparse._ActionsContainer) -> None:
    """Add arguments related to output format to the command-line parser.

    These are mutually exclusive options that each will set the
    .output_format member to a one of the available OutputFormat values.
    If not given, the .output_format member will remain unset, to allow the
    underlying default to come through.
    """
    parser.add_argument(
        "--summary",
        dest="output_format",
        action="store_const",
        const="human_summary",
        help="Generate human-readable summary report (default)",
    )
    parser.add_argument(
        "--detailed",
        dest="output_format",
        action="store_const",
        const="human_detailed",
        help="Generate human-readable detailed report",
    )
    parser.add_argument(
        "--json",
        dest="output_format",
        action="store_const",
        const="json",
        help="Generate JSON output instead of a human-readable report",
    )


def populate_parser_paths_options(parser: argparse._ActionsContainer) -> None:
    """Add the source paths (code, deps, pyenv) Settings members to the parser.

    None of these options should specify default values
    (and the parser-wide default value should be argparse.SUPPRESS).
    This ensures that unspecified options are _omitted_ from the resulting
    argparse.Namespace object, which will allow the underlying defaults
    from Settings to come through when we create the Settings object in
    .create() below.
    """
    parser.add_argument(
        "basepaths",
        type=lambda p: None if p == argparse.SUPPRESS else Path(p),
        nargs="*",
        help=(
            "Optional directories in which to search for code (imports),"
            " dependency declarations and/or Python environments. Defaults to"
            " the current directory."
        ),
    )
    parser.add_argument(
        "--code",
        nargs="+",
        action="union",
        type=parse_path_or_stdin,
        metavar="PATH_OR_STDIN",
        help=(
            "Code to parse for import statements (files or directories, or use"
            " '-' to read code from stdin). Defaults to basepaths (see above)."
        ),
    )
    parser.add_argument(
        "--deps",
        nargs="+",
        action="union",
        type=Path,
        metavar="PATH",
        help=(
            "Where to find dependency declarations (files or directories)."
            " Defaults to finding supported files under basepaths (see above)."
        ),
    )
    parser.add_argument(
        "--deps-parser-choice",
        type=read_parser_choice,
        choices=list(ParserChoice),
        help=(
            "Name of the parsing strategy to use for dependency declarations,"
            " useful for when the file to parse doesn't match a standard name"
        ),
    )
    parser.add_argument(
        "--pyenv",
        dest="pyenvs",
        nargs="+",
        action="union",
        type=Path,
        metavar="PYENV_DIR",
        help=(
            "Where to search for Python environments that have project"
            " dependencies installed. Defaults to searching under basepaths"
            " (see above)."
        ),
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        action="union",
        metavar="PATTERN",
        help=(
            "Exclude patterns (.gitignore format) to apply when looking for code"
            " (imports), dependency declarations and/or Python environments."
            " Defaults to '.*', meaning that hidden/dot paths are excluded."
        ),
    )
    parser.add_argument(
        "--exclude-from",
        nargs="+",
        action="union",
        type=Path,
        metavar="PATH",
        help=(
            "Files containing exclude patterns to apply when looking for code"
            " (imports), dependency declarations and/or Python environments."
        ),
    )
    parser.add_argument(
        "--install-deps",
        dest="install_deps",
        action="store_true",
        help=(
            "Allow FawltyDeps to auto-install declared dependencies into a"
            " separate temporary virtualenv to discover the imports they expose."
        ),
    )
    parser.add_argument(
        "--custom-mapping-file",
        nargs="+",
        action="union",
        type=Path,
        metavar="FILE_PATH",
        help=(
            "Path to toml file containing mapping of dependencies to imports"
            " defined by the user."
        ),
    )


def populate_parser_configuration(parser: argparse._ActionsContainer) -> None:
    """Add configuration Settings members to the command-line parser.

    Only `config-file` may specify default values.
    Verbosity-related options do not correspond directly to a Settings member,
    but the latter is subtracted from the former to make .verbosity.
    """
    parser.add_argument(
        "--config-file",
        type=Path,
        default=Path("./pyproject.toml"),
        help="Where to find FawltyDeps config (default: ./pyproject.toml)",
    )
    parser.add_argument(
        "--ignore-undeclared",
        nargs="+",
        action="union",
        metavar="IMPORT_NAME",
        help=(
            "Imports to ignore when looking for undeclared"
            " dependencies, e.g. --ignore-undeclared isort pkg_resources"
        ),
    )
    parser.add_argument(
        "--ignore-unused",
        nargs="+",
        action="union",
        metavar="DEP_NAME",
        help=(
            "Specify a list of dependencies to ignore when looking for unused"
            " dependencies. By default, this list includes common development tools."
            " Use this option to customize the list,"
            " e.g. --ignore-unused pylint black some_other_module"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        help="Increase log level (WARNING by default, -v: INFO, -vv: DEBUG)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="count",
        help="Decrease log level (WARNING by default, -q: ERROR, -qq: FATAL)",
    )


def populate_parser_other_options(parser: argparse._ActionsContainer) -> None:
    """Add options not related to the Settings object."""
    parser.add_argument(
        "--generate-toml-config",
        action="store_true",
        default=False,
        help="Print a TOML config section with the current settings, and exit",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"FawltyDeps v{version()}",
        help="Print the version number of FawltyDeps",
    )
    # build_parser() removes the automatic `--help` option so that we
    # can control exactly where it's added. Here we add it back:
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit",
    )


def build_parser(
    description: str = "",
) -> argparse.ArgumentParser:
    """Create command-line parser object and populate it with arguments.

    Return the parser itself (which the caller will use to parse/collect
    command-line arguments), as well as a suitable argument group where the
    caller can add its own additional command-line arguments.
    """
    parser = argparse.ArgumentParser(
        prog=__name__.split(".", maxsplit=1)[0],  # use top-level package name
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,  # instead, add --help in populate_parser_other_options()
        argument_default=argparse.SUPPRESS,
    )

    parser.register("action", "union", ArgparseUnionAction)

    # A mutually exclusive group for arguments specifying .actions
    action_group = parser.add_argument_group(
        title="Actions (choose one)"
    ).add_mutually_exclusive_group()
    populate_parser_actions(action_group)

    # A mutually exclusive group for arguments specifying .output_format
    output_format_group = parser.add_argument_group(
        title="Output format (choose one)"
    ).add_mutually_exclusive_group()
    populate_output_formats(output_format_group)

    # A group for source paths options
    source_group = parser.add_argument_group(title="Source paths options")
    populate_parser_paths_options(source_group)

    # A group for fawltydeps configuration options
    config_group = parser.add_argument_group(title="Configuration options")
    populate_parser_configuration(config_group)

    # A different group for the other options.
    option_group = parser.add_argument_group(title="Other options")
    populate_parser_other_options(option_group)

    return parser
