"""Test unhappy path, where parsing of dependencies fails"""

import logging
from pathlib import Path
from textwrap import dedent

import pytest

from fawltydeps.extract_declared_dependencies import (
    extract_declared_dependencies,
    parse_setup_cfg_contents,
    parse_setup_contents,
)
from fawltydeps.types import Location, UnparseablePathException


def test_extract_declared_dependencies__unsupported_file__raises_error(
    project_with_setup_and_requirements,
):
    with pytest.raises(UnparseablePathException):
        list(
            extract_declared_dependencies(
                [project_with_setup_and_requirements / "python_file.py"]
            )
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


@pytest.mark.parametrize(
    "code,expect,fail_arg",
    [
        pytest.param(
            """\
            from setuptools import setup

            generate_requirements = lambda n: [f"mock-requirement-{k}" for k in range(n)]
            setup(
                name="MyLib",
                install_requires=generate_requirements(4)
            )
            """,
            [],
            "install_requires",
            id="lambda_call_in_install_requires",
        ),
        pytest.param(
            """\
            from setuptools import setup

            generate_requirements = lambda n: {
                f"extra{k}": f"mock-requirement-{k}" for k in range(n)
            }
            setup(
                name="MyLib",
                extras_require=generate_requirements(4)
            )
            """,
            [],
            "extras_require",
            id="lambda_call_in_extras_require",
        ),
        pytest.param(
            """\
            from setuptools import setup

            generate_requirements = lambda n: [f"mock-requirement-{k}" for k in range(n)]
            setup(
                name="MyLib",
                extras_require={
                    "simple_parsing": ["abc"],
                    "complex_parsing": generate_requirements(3)
                    }
            )
            """,
            [],
            "extras_require",
            id="lambda_call_inside_extras_require_dict",
        ),
        pytest.param(
            """\
            from setuptools import setup

            # my_deps is unset

            setup(
                name="MyLib",
                install_requires=my_deps,
            )
            """,
            [],
            "install_requires",
            id="reference_to_unset_variable",
        ),
        pytest.param(
            """\
            from setuptools import setup

            my_deps = [my_deps]

            setup(
                name="MyLib",
                install_requires=my_deps,
            )
            """,
            [],
            "install_requires",
            id="unresolvable_self_reference",
        ),
    ],
)
def test_parse_setup_contents__cannot_parse__logs_warning(
    caplog, code, expect, fail_arg
):
    caplog.set_level(logging.WARNING)
    result = list(parse_setup_contents(dedent(code), Location(Path("setup.py"))))
    assert f"Could not parse contents of `{fail_arg}`" in caplog.text
    assert "setup.py" in caplog.text
    assert expect == result
