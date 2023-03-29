"""FawltyDeps configuration and command-line options."""
import argparse
import json
import logging
import sys
from enum import Enum
from functools import total_ordering
from pathlib import Path
from typing import ClassVar, List, Optional, Set, TextIO, Tuple, Type, Union

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
    output_format: OutputFormat = OutputFormat.HUMAN_SUMMARY
    code: Set[PathOrSpecial] = {Path(".")}
    deps: Set[Path] = {Path(".")}
    pyenv: Optional[Path] = None
    ignore_undeclared: Set[str] = set()
    ignore_unused: Set[str] = set()
    deps_parser_choice: Optional[ParserChoice] = None
    install_deps: bool = False
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

        base_paths = set(getattr(cmdline_args, "basepaths", []))
        if base_paths:
            code_paths = args_dict.setdefault("code", base_paths)
            deps_paths = args_dict.setdefault("deps", base_paths)
            if code_paths != base_paths and deps_paths != base_paths:
                msg = (
                    "All three path specifications (code, deps, and base)"
                    f"have been used. Use at most 2. basepaths={base_paths}, "
                    f"code_paths={code_paths}, deps_paths={deps_paths}"
                )
                raise argparse.ArgumentError(argument=None, message=msg)

        # Use subset of args_dict that directly correspond to fields in Settings
        ret = {opt: arg for opt, arg in args_dict.items() if opt in cls.__fields__}

        # If user gives --verbose or --quiet on the command line, we _override_
        # any pre-configured verbosity value
        if {"verbose", "quiet"}.intersection(args_dict.keys()):
            ret["verbosity"] = args_dict.get("verbose", 0) - args_dict.get("quiet", 0)

        return cls(**ret)


def print_toml_config(settings: Settings, out: TextIO = sys.stdout) -> None:
    """Serialize the given Settings object into a TOML config section."""
    # Use JSON serialization as a basis for TOML output. Load that back into
    # Python and then use Python's repr() representation below
    simple_settings = json.loads(settings.json())
    defaults = {
        name: field.default for name, field in settings.__class__.__fields__.items()
    }
    try:
        has_default_value = {
            name: getattr(settings, name) == default
            for name, default in defaults.items()
        }
    except AttributeError:
        logger.critical(f"Sanity check failed: {settings!r} is missing a field!")
        raise

    lines = [
        "# Copy this TOML section into your pyproject.toml to configure FawltyDeps",
        "# (default values are commented)",
        "[tool.fawltydeps]",
    ] + [
        f"{'# ' if has_default_value[name] else ''}{name} = {value!r}"
        for name, value in simple_settings.items()
    ]
    print("\n".join(lines), file=out)
