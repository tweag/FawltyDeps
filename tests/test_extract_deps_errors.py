"""Test unhappy path, where parsing of dependencies fails."""

import logging

import pytest

from fawltydeps.extract_deps.setup_cfg_parser import parse_setup_cfg
from fawltydeps.extract_deps.setup_py_parser import parse_setup_py
from fawltydeps.types import Location


def test_parse_setup_cfg__malformed__logs_error(write_tmp_files, caplog):
    tmp_path = write_tmp_files(
        {
            "setup.cfg": """\
                [options
                install_requires =
                    pandas
                """,
        }
    )
    expected = []
    caplog.set_level(logging.ERROR)

    path = tmp_path / "setup.cfg"
    result = list(parse_setup_cfg(path))
    assert f"Could not parse contents of `{Location(path)}`" in caplog.text
    assert expected == result


@pytest.mark.parametrize(
    ("code", "expect", "fail_arg"),
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
def test_parse_setup_py__cannot_parse__logs_warning(
    write_tmp_files, caplog, code, expect, fail_arg
):
    tmp_path = write_tmp_files({"setup.py": code})
    path = tmp_path / "setup.py"

    caplog.set_level(logging.WARNING)
    result = list(parse_setup_py(path))
    assert f"Could not parse contents of `{fail_arg}`" in caplog.text
    assert str(path) in caplog.text
    assert expect == result
