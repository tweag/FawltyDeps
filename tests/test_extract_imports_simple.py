"""Test that we can extract simple imports from Python code."""

from textwrap import dedent

from fawltydeps.extract_imports import parse_code, parse_dir, parse_file


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


def test_parse_dir_with_mix_of_python_and_nonpython(tmp_path):
    code1 = dedent("""\
        from pathlib import Path
        import sys

        import numpy as np

        def foo():
            pass
        """)
    (tmp_path / "test1.py").write_text(code1)

    code2 = dedent("""\
        import sys

        import pandas

        import test1

        foo()
        """)
    (tmp_path / "test2.py").write_text(code2)

    not_code = dedent("""\
        This is not code, even if it contains the
        import word.
        """)
    (tmp_path / "not_python.txt").write_text(not_code)

    expect = {"pathlib", "sys", "numpy", "pandas", "test1"}
    assert set(parse_dir(tmp_path)) == expect


def test_parse_dir_imports_are_returned_in_order_of_encounter(tmp_path):
    first = dedent("""\
        from pathlib import Path
        import sys

        import foo
        """)
    (tmp_path / "first.py").write_text(first)

    second = dedent("""\
        import sys

        from foo import bar, baz
        import xyzzy
        """)
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir/second.py").write_text(second)

    expect = ["pathlib", "sys", "foo", "sys", "foo", "xyzzy"]
    assert list(parse_dir(tmp_path)) == expect
