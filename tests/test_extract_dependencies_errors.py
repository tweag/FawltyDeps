"Test unhappy path, where parsing of dependencies fails"
from pathlib import Path
from textwrap import dedent

import pytest

from fawltydeps.extract_dependencies import parse_setup_cfg_contents


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
