"""FawltyDeps configuration and command-line options."""
import argparse
import logging
import sys
from enum import Enum
from functools import total_ordering
from pathlib import Path
from typing import ClassVar, List, Optional, Set, Tuple, Type, Union

from pydantic import BaseSettings
from pydantic.env_settings import SettingsSourceCallable  # pylint: disable=E0611

from fawltydeps.types import PathOrSpecial, TomlData

if sys.version_info >= (3, 11):
    import tomllib  # pylint: disable=no-member
else:
    import tomli as tomllib

logger = logging.getLogger(__name__)


class PyprojectTomlSettingsSource:
    """A custom settings source that loads settings from pyproject.toml."""

    def __init__(self, path: Optional[Path], section: str):
        self.path = path
        self.section = section

    def get_section(self, toml_data: TomlData) -> TomlData:
        """Find 'self.section' in the given TOML data and return it."""
        for key in self.section.split("."):
            toml_data = toml_data[key]
        return toml_data

    def __call__(self, _settings: BaseSettings) -> TomlData:
        """Read pyproject.toml and return relevant settings within."""
        if self.path is None:  # skip reading config file
            return {}

        try:
            with self.path.open("rb") as config_file:
                toml_data = tomllib.load(config_file)
            return self.get_section(toml_data)
        except (KeyError, FileNotFoundError) as exc:
            logger.info(f"Failed to load configuration file: {exc}")
        return {}


@total_ordering
class OrderedEnum(Enum):
    """Encapsulate an orderable (aka. sortable) enum."""

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, OrderedEnum):
            return NotImplemented
        values: List["OrderedEnum"] = list(self.__class__)
        return values.index(self) < values.index(other)


class Action(OrderedEnum):
    """Actions provided by the FawltyDeps application."""

    LIST_IMPORTS = "list_imports"
    LIST_DEPS = "list_deps"
    REPORT_UNDECLARED = "check_undeclared"
    REPORT_UNUSED = "check_unused"


class OutputFormat(OrderedEnum):
    """Output formats provided by the FawltyDeps application."""

    HUMAN_SUMMARY = "human_summary"
    HUMAN_DETAILED = "human_detailed"
    JSON = "json"


class ParserChoice(Enum):
    """Enumerate the choices of dependency declaration parsers."""

    REQUIREMENTS_TXT = "requirements.txt"
    SETUP_PY = "setup.py"
    SETUP_CFG = "setup.cfg"
    PYPROJECT_TOML = "pyproject.toml"

    def __str__(self) -> str:
        return self.value


def read_parser_choice(filename: str) -> ParserChoice:
    """Read the command-line argument for manual parser choice."""
    for choice in ParserChoice:
        if choice.value == filename:
            return choice
    raise ValueError(f"Unrecognized dependency parser choice: {filename}")


def parse_path_or_stdin(arg: str) -> PathOrSpecial:
    """Convert --code argument into Path or "<stdin>"."""
    if arg == "-":
        return "<stdin>"
    return Path(arg)


class Settings(BaseSettings):  # type: ignore
    """FawltyDeps settings.

    Below, you find the defaults, these can be overridden in multiple ways:
    - By setting directives in the [tool.fawltydeps] section in pyproject.toml.
    - By setting fawltydeps_* environment variables
    - By passing command-line arguments

    TODO? Currently overrides happen _completely_, for example specifying
    --ignore-undeclared on the command-line will _replace_ an ignore_undeclared
    directive in pyproject.toml. We may want to consider allowing some
    directives to _combine_ (although that will carry further complications).
    """

    actions: Set[Action] = {Action.REPORT_UNDECLARED, Action.REPORT_UNUSED}
    code: PathOrSpecial = Path(".")
    deps: Path = Path(".")
    output_format: OutputFormat = OutputFormat.HUMAN_SUMMARY
    ignore_undeclared: Set[str] = set()
    ignore_unused: Set[str] = set()
    deps_parser_choice: Optional[ParserChoice] = None
    verbosity: int = 0

    # Class vars: these can not be overridden in the same way as above, only by
    # passing keyword args to Settings.config(). This is because they change the
    # way in which we build the Settings object itself.
    config_file: ClassVar[Optional[Path]] = None
    config_section: ClassVar[str] = "tool.fawltydeps"

    class Config:
        """Pydantic configuration for Settings class."""

        allow_mutation = False  # make it immutable, once created
        extra = "forbid"  # fail if we pass unsupported Settings fields
        env_prefix = "fawltydeps_"  # interpret $fawltydeps_* in env as settings

        # From pydantic's docs (https://docs.pydantic.dev/usage/settings/):
        # pydantic ships with multiple built-in settings sources.
        # However, you may occasionally need to add your own custom sources,
        # 'customise_sources' makes this very easy:

        @classmethod
        def customise_sources(
            cls,
            init_settings: SettingsSourceCallable,
            env_settings: SettingsSourceCallable,
            file_secret_settings: SettingsSourceCallable,  # pylint: disable=W0613
        ) -> Tuple[SettingsSourceCallable, ...]:
            """Select and prioritize the various configuration sources."""
            # Use class vars in Settings to determine which configuration file
            # we read.
            config_file_settings = PyprojectTomlSettingsSource(
                path=Settings.config_file,
                section=Settings.config_section,
            )
            return (
                init_settings,  # from command-line (see main.py)
                env_settings,  # from environment variables
                config_file_settings,  # from config file
            )

    @classmethod
    def config(cls, **kwargs: Union[None, Path, str]) -> Type["Settings"]:
        """Configure the class variables in this Settings class.

        This must be done _before_ instantiating Settings objects, as the
        class variables affect how this instantiation is done (e.g. which
        configuration file is read).
        """
        for key, value in kwargs.items():
            assert key in cls.__class_vars__
            setattr(cls, key, value)
        return cls

    @classmethod
    def create(cls, cmdline_args: argparse.Namespace) -> "Settings":
        """Convert the parsed command-line args into a Settings object.

        Extract the relevant parts of the given argparse.Namespace object into
        a dict of keyword args that we can pass to the Settings constructor.
        This dict must _only_ contain the Settings members that we want to
        _override_ from the command-line. Any Settings members that should
        retain their underlying values (from environment, config file, or -
        ultimately - from the hardcoded defaults above) must NOT appear in
        these keyword args (cf. use of argparse.SUPPRESS above).
        """
        args_dict = cmdline_args.__dict__

        # Use subset of args_dict that directly correspond to fields in Settings
        ret = {arg: value for arg, value in args_dict.items() if arg in cls.__fields__}

        # If user gives --verbose or --quiet on the command line, we _override_
        # any pre-configured verbosity value
        if {"verbose", "quiet"}.intersection(args_dict.keys()):
            ret["verbosity"] = args_dict.get("verbose", 0) - args_dict.get("quiet", 0)

        return cls(**ret)


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
        "--list-imports",
        dest="actions",
        action="store_const",
        const={Action.LIST_IMPORTS},
        help="List third-party imports extracted from code and exit",
    )
    parser.add_argument(
        "--list-deps",
        dest="actions",
        action="store_const",
        const={Action.LIST_DEPS},
        help="List declared dependencies and exit",
    )


def populate_output_formats(parser: argparse._ActionsContainer) -> None:
    """Add arguments related to output format to the command-line parser.

    These are mutually exclusive options that each will set the
    .output_format member to a one of the available OutputFormat values.
    If not given, the .output_format member will remain unset, to allow the
    underlying default to come through.
    """
    output_format = parser.add_mutually_exclusive_group()
    output_format.add_argument(
        "--summary",
        dest="output_format",
        action="store_const",
        const="human_summary",
        help="Generate human-readable summary report (default)",
    )
    output_format.add_argument(
        "--detailed",
        dest="output_format",
        action="store_const",
        const="human_detailed",
        help="Generate human-readable detailed report",
    )
    output_format.add_argument(
        "--json",
        dest="output_format",
        action="store_const",
        const="json",
        help="Generate JSON output instead of a human-readable report",
    )


def populate_parser_options(parser: argparse._ActionsContainer) -> None:
    """Add the other Settings members to the command-line parser.

    Except where otherwise noted, these map directly onto a corresponding
    Settings member. None of these options should specify default values
    (and the parser-wide default value should be argparse.SUPPRESS). This
    ensures that unspecified options are _omitted_ from the resulting
    argparse.Namespace object, which will allow the underlying defaults
    from Settings to come through when we create the Settings object in
    .create() below.
    """
    parser.add_argument(
        "--code",
        type=parse_path_or_stdin,
        help=(
            "Code to parse for import statements (file or directory, use '-' "
            "to read code from stdin; defaults to the current directory)"
        ),
    )
    parser.add_argument(
        "--deps",
        type=Path,
        help=(
            "Where to find dependency declarations (file or directory, defaults"
            " to looking for supported files in the current directory)"
        ),
    )
    parser.add_argument(
        "--ignore-undeclared",
        nargs="+",
        metavar="IMPORT_NAME",
        help=(
            "Imports to ignore when looking for undeclared"
            " dependencies, e.g. --ignore-undeclared isort pkg_resources"
        ),
    )
    parser.add_argument(
        "--ignore-unused",
        nargs="+",
        metavar="DEP_NAME",
        help=(
            "Dependencies to ignore when looking for unused"
            " dependencies, e.g. --ignore-unused pylint black"
        ),
    )
    parser.add_argument(
        "--deps-parser-choice",
        type=read_parser_choice,
        choices=list(ParserChoice),
        help=(
            "Name of the parsing strategy to use for dependency declarations, "
            "useful for when the file to parse doesn't match a standard name"
        ),
    )

    # The following two do not correspond directly to a Settings member,
    # but the latter is subtracted from the former to make .verbosity.
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


def setup_cmdline_parser(
    description: str,
) -> Tuple[argparse.ArgumentParser, argparse._ArgumentGroup]:
    """Create command-line parser object and populate it with arguments.

    Return the parser itself (which the caller will use to parse/collect
    command-line arguments), as well as a suitable argument group where the
    caller can add its own additional command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,  # instead, add --help in the "Options" group below
        argument_default=argparse.SUPPRESS,
    )

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

    # A different group for the other options.
    option_group = parser.add_argument_group(title="Other options")
    populate_parser_options(option_group)
    option_group.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit",
    )

    return parser, option_group
