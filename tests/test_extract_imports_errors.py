"""Verify graceful failure when we cannot extract imports from Python code."""

from textwrap import dedent

import pytest

from fawltydeps.extract_imports import parse_code, parse_dir, parse_file


def test_parse_code_failures_propagates_SyntaxError():
    code = dedent("""\
        This is not Python code
        """)
    with pytest.raises(SyntaxError):
        list(parse_code(code))
