"Test unhappy path, where parsing of dependencies fails"
import logging
from pathlib import Path
from textwrap import dedent

import pytest

from fawltydeps.extract_dependencies import (
    extract_dependencies,
    parse_setup_cfg_contents,
)
from fawltydeps.types import ArgParseError, Location


def test_extract_dependencies__unsupported_file__raises_error(
    project_with_setup_and_requirements,
):
    with pytest.raises(ArgParseError):
        list(
            extract_dependencies(project_with_setup_and_requirements / "python_file.py")
        )


def test_parse_setup_cfg_contents__malformed__logs_error(caplog):
    setup_contents = dedent(
        """\
        [options
        install_requires =
            pandas
        """
    )
    expected = []
    caplog.set_level(logging.ERROR)

    source = Location(Path("setup.cfg"))
    result = list(parse_setup_cfg_contents(setup_contents, source))
    assert f"Could not parse contents of `{source}`" in caplog.text
    assert expected == result
