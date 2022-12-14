"""Test that we can extract simple imports from Python code."""

from textwrap import dedent

from fawltydeps.parser import parse_imports


def test_stdlib_import():
    code = dedent("""\
        import sys

        print(sys.executable)
        """)
    expect = {"sys"}
    assert set(parse_imports(code)) == expect
