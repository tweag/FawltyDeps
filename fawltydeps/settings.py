"""FawltyDeps configuration and command-line options."""
import logging
import sys
from enum import Enum
from pathlib import Path
from typing import ClassVar, Optional, Set, Tuple, Type, Union

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


class Action(Enum):
    """Actions provided by the FawltyDeps application."""

    LIST_IMPORTS = "list_imports"
    LIST_DEPS = "list_deps"
    REPORT_UNDECLARED = "check_undeclared"
    REPORT_UNUSED = "check_unused"


class ParserChoice(Enum):
    """Enumerate the choices of dependency declaration parsers."""

    REQUIREMENTS_TXT = "requirements.txt"
    SETUP_PY = "setup.py"
    SETUP_CFG = "setup.cfg"
    PYPROJECT_TOML = "pyproject.toml"

    def __str__(self) -> str:
        return self.value


class Settings(BaseSettings):  # type: ignore
    """FawltyDeps settings.

    Below, you find the defaults, these can be overridden in multiple ways:
    - By setting directives in the [tool.fawltydeps] section in pyproject.toml.
    - By setting fawltydeps_* environment variables
    - By passing command-line arguments
    """

    actions: Set[Action] = {Action.REPORT_UNDECLARED, Action.REPORT_UNUSED}
    code: PathOrSpecial = Path(".")
    deps: Path = Path(".")
    json_output: bool = False
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
