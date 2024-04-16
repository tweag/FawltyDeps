"""FawltyDeps configuration and command-line options."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from enum import Enum
from functools import partial, total_ordering
from pathlib import Path
from typing import ClassVar, List, Optional, Set, TextIO, Tuple, Type, Union

try:  # import from Pydantic V2
    from pydantic.v1 import BaseSettings
    from pydantic.v1.env_settings import SettingsSourceCallable
    from pydantic.v1.json import custom_pydantic_encoder
except ModuleNotFoundError:
    from pydantic import BaseSettings  # type: ignore[no-redef]
    from pydantic.env_settings import SettingsSourceCallable  # type: ignore[no-redef]
    from pydantic.json import custom_pydantic_encoder  # type: ignore[no-redef]

from fawltydeps.types import CustomMapping, ParserChoice, PathOrSpecial, TomlData

if sys.version_info >= (3, 11):
    import tomllib
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
        values: List[OrderedEnum] = list(self.__class__)
        return values.index(self) < values.index(other)


class Action(OrderedEnum):
    """Actions provided by the FawltyDeps application."""

    LIST_SOURCES = "list_sources"
    LIST_IMPORTS = "list_imports"
    LIST_DEPS = "list_deps"
    REPORT_UNDECLARED = "check_undeclared"
    REPORT_UNUSED = "check_unused"


class OutputFormat(OrderedEnum):
    """Output formats provided by the FawltyDeps application."""

    HUMAN_SUMMARY = "human_summary"
    HUMAN_DETAILED = "human_detailed"
    JSON = "json"


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


DEFAULT_IGNORE_UNUSED = {
    # Development tools not meant to be imported
    # Formatting Tools
    "autopep8",
    "black",
    "codespell",
    "isort",
    "pyformat",
    "yapf",
    # Linting Tools
    "flake8",
    "mccabe",
    "mypy",
    "pyflakes",
    "pylint",
    "pyright",
    "ruff",
    # Security Tools
    "bandit",
    # Documentation Tools
    "myst-parser",
    "recommonmark",
    "sphinx",
    # Testing Tools
    "coverage",
    "fawltydeps",
    "nox",
    "pre-commit",
    "pytest",
    "tox",
    # Building and Packaging Tools
    "twine",
    "wheel",
    # Utility Tools
    "pydocstyle",
    "rope",
    "unify",
}


class Settings(BaseSettings):
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
    code: Set[PathOrSpecial] = {Path()}
    deps: Set[Path] = {Path()}
    pyenvs: Set[Path] = {Path()}
    custom_mapping: Optional[CustomMapping] = None
    ignore_undeclared: Set[str] = set()
    ignore_unused: Set[str] = DEFAULT_IGNORE_UNUSED
    deps_parser_choice: Optional[ParserChoice] = None
    install_deps: bool = False
    exclude: Set[str] = {".*"}
    exclude_from: Set[Path] = set()
    verbosity: int = 0
    custom_mapping_file: Set[Path] = set()

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
            file_secret_settings: SettingsSourceCallable,  # noqa: ARG003
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
    def config(cls, **kwargs: Union[None, Path, str]) -> Type[Settings]:
        """Configure the class variables in this Settings class.

        This must be done _before_ instantiating Settings objects, as the
        class variables affect how this instantiation is done (e.g. which
        configuration file is read).
        """
        for key, value in kwargs.items():
            assert key in cls.__class_vars__  # noqa: S101, sanity check
            setattr(cls, key, value)
        return cls

    @classmethod
    def create(cls, cmdline_args: argparse.Namespace) -> Settings:
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
            pyenv_paths = args_dict.setdefault("pyenvs", base_paths)
            if base_paths not in (code_paths, deps_paths, pyenv_paths):
                msg = (
                    "All four path specifications (code, deps, pyenvs, and base)"
                    f"have been used. Use at most 3. basepaths={base_paths}, "
                    f"code_paths={code_paths}, deps_paths={deps_paths}, "
                    f"pyenv_paths={pyenv_paths}"
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
    set_sort = partial(sorted, key=str)
    encoder = partial(custom_pydantic_encoder, {frozenset: set_sort, set: set_sort})
    simple_settings = json.loads(json.dumps(settings, default=encoder))
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

    dictionary_options = {"custom_mapping"}

    def _option_to_toml(name, value) -> str:  # type: ignore[no-untyped-def]  # noqa: ANN001
        """Serialize options to toml configuration entries.

        Options that are of dictionary type must be given a section entry.
        Assumption: dictionaries options are not nested.
        """
        toml_value_map = {
            "None": "...",  # always commented, see sanity check below
            "False": "false",
            "True": "true",
            # add more values here for which repr(value) is not valid TOML
        }

        if value is None:
            # sanity check: None values are represented in TOML by omission,
            # hence make sure these are always commented (i.e. equal to default)
            assert has_default_value[name]  # noqa: S101

        prefix = "# " if has_default_value[name] else ""

        if name in dictionary_options:
            toml_option = f"{prefix}[tool.fawltydeps.{name}]"
            if value is not None:
                toml_option += "".join(
                    [
                        f"\n{prefix}{k} = {toml_value_map.get(repr(v), repr(v))}"
                        for k, v in value.items()
                    ]
                )
        else:
            toml_value = toml_value_map.get(repr(value), repr(value))
            toml_option = f"{prefix}{name} = {toml_value}"
        return toml_option

    lines = (
        [
            "# Copy this TOML section into your pyproject.toml to configure FawltyDeps",
            "# (default values are commented)",
            "[tool.fawltydeps]",
        ]
        + [
            _option_to_toml(name, value)
            for name, value in simple_settings.items()
            # First handle non-dictionary options, as we don't want them to end
            # up inside the config section resulting from a dictionary option.
            if name not in dictionary_options
        ]
        + [
            _option_to_toml(name, value)
            for name, value in simple_settings.items()
            # Export dictionary options as separate TOML  config sections
            if name in dictionary_options
        ]
    )
    print("\n".join(lines), file=out)
