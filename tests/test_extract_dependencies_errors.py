"Test unhappy path, where parsing of dependencies fails"
from pathlib import Path
from textwrap import dedent

import pytest

from fawltydeps.extract_dependencies import (
    extract_dependencies,
    parse_setup_cfg_contents,
)
from fawltydeps.types import ArgParseError


def test_parse_setup_cfg_contents__malformed__fails():

    file_content = (
        dedent(
            """\
            [options]
            install_requires = pandas
            """
        ),
    )
    file_name = Path("setup.cfg")
    with pytest.raises(TypeError):
        list(parse_setup_cfg_contents(file_content, file_name))


def test_extract_dependencies__unsupported_file__raises_error(
    project_with_setup_and_requirements,
):
    with pytest.raises(ArgParseError):
        list(
            extract_dependencies(
                project_with_setup_and_requirements.joinpath("python_file.py")
            )
        )
