"""Test that we can extract simple imports from Python code."""

from textwrap import dedent

from fawltydeps.extract_imports import parse_code, parse_file


def test_stdlib_import():
    code = dedent("""\
        import sys

        print(sys.executable)
        """)
    expect = {"sys"}
    assert set(parse_code(code)) == expect


def test_stdlib_two_imports():
    code = dedent("""\
        import platform, sys

        print(sys.executable, platform.python_version())
        """)
    expect = {"platform", "sys"}
    assert set(parse_code(code)) == expect


def test_stdlib_import_from():
    code = dedent("""\
        from sys import executable

        print(executable)
        """)
    expect = {"sys"}
    assert set(parse_code(code)) == expect


def test_combinations_of_simple_imports():
    code = dedent("""\
        from pathlib import Path
        import sys
        import unittest as obsolete

        import requests
        from foo import bar, baz
        import numpy as np
        """)
    expect = {"pathlib", "sys", "unittest", "requests", "foo", "numpy"}
    assert set(parse_code(code)) == expect


def test_parse_single_file(tmp_path):
    code = dedent("""\
        from pathlib import Path
        import sys
        import unittest as obsolete

        import requests
        from foo import bar, baz
        import numpy as np
        """)
    script = tmp_path / "test.py"
    script.write_text(code)

    expect = {"pathlib", "sys", "unittest", "requests", "foo", "numpy"}
    assert set(parse_file(script)) == expect
