"""Test that we can extract imports + deps from PEP 723-compliant scripts."""

from textwrap import dedent

import pytest


@pytest.mark.parametrize(
    ("code", "expect_declared_deps", "expect_imports"),
    [
        pytest.param(
            dedent(
                """\
                # /// script
                # requires-python = ">=3.11"
                # dependencies = [
                #   "requests<3",
                #   "rich",
                # ]
                # ///
                
                import requests
                from rich.pretty import pprint
                
                resp = requests.get("https://peps.python.org/api/peps.json")
                data = resp.json()
                pprint([(k, v["title"]) for k, v in data.items()][:10])
                """
            ),
            {"requests", "rich"},
            {"requests", "rich"},
            id="example_from_pep723",
        ),
    ],
)
def test_parse_pep723_code(code, expected_declared_deps, expect_imports):
    assert False
