"""Code for parsing setup.cfg files."""

import configparser
import logging
from dataclasses import replace
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator

from fawltydeps.types import DeclaredDependency, Location

from .requirements_parser import parse_requirements_txt

logger = logging.getLogger(__name__)


def parse_setup_cfg(path: Path) -> Iterator[DeclaredDependency]:
    """Extract dependencies (package names) from setup.cfg.

    `ConfigParser` basic building blocks are "sections"
    which are marked by "[..]" in the configuration file.
    Requirements are declared as main dependencies (install_requires),
    extra dependencies (extras_require) and tests dependencies (tests_require).
    See https://setuptools.pypa.io/en/latest/userguide/declarative_config.html
    section: configuring-setup-using-setup-cfg-files for more details.
    The declaration uses `section` + `option` syntax where section may be [options]
    or [options.{requirements_type}].
    """
    source = Location(path)
    parser = configparser.ConfigParser()
    try:
        parser.read([path])
    except configparser.Error as exc:
        logger.debug(exc)
        logger.error("Could not parse contents of `%s`", source)
        return

    def parse_value(value: str) -> Iterator[DeclaredDependency]:
        # Ugly hack since parse_requirements_txt() accepts only a path.
        # TODO: try leveraging RequirementsFile.from_string once
        #       pip-requirements-parser updates.
        # See:  https://github.com/nexB/pip-requirements-parser/pull/17

        # https://github.com/nexB/pip-requirements-parser/pull/19#discussion_r1379279880
        temp_file = NamedTemporaryFile(  # noqa: SIM115
            "wt",
            delete=False,
            # we prefer utf8 encoded strings, but ...
            # - must not change newlines
            # - must not  change encoding, fallback to system encoding for compatibility
            newline="",
            encoding=None,
        )
        temp_file.write(value)
        temp_file.close()
        try:
            for dep in parse_requirements_txt(Path(temp_file.name)):
                yield replace(dep, source=source)
        finally:
            Path(temp_file.name).unlink()

    def extract_section(section: str) -> Iterator[DeclaredDependency]:
        if section in parser:
            for option in parser.options(section):
                value = parser.get(section, option)
                logger.debug("Dependencies found in [%s]: %s", section, value)
                yield from parse_value(value)

    def extract_option_from_section(
        section: str, option: str
    ) -> Iterator[DeclaredDependency]:
        if section in parser and option in parser.options(section):
            value = parser.get(section, option)
            logger.debug("Dependencies found in [%s] / %s: %s", section, option, value)
            yield from parse_value(value)

    # Parse [options] -> install_requires
    yield from extract_option_from_section("options", "install_requires")

    # Parse [options] -> extras_require, or [options.extras_require]
    yield from extract_option_from_section("options", "extras_require")
    yield from extract_section("options.extras_require")

    # Parse [options] -> tests_require, or [options.tests_require]
    yield from extract_option_from_section("options", "tests_require")
    yield from extract_section("options.tests_require")
