"""Test that we can extract simple imports from Python code."""

from pathlib import Path
from textwrap import dedent
from typing import List, Optional

from fawltydeps.extract_imports import ParsedImport, parse_code, parse_dir, parse_file


def with_location(imports: List[str], location: Optional[Path]) -> List[ParsedImport]:
    return [ParsedImport(i, location) for i in imports]


def test_parse_code__no_code__has_no_imports():
    code = ""
    expect = []
    assert set(parse_code(code)) == set(expect)


def test_parse_code__stdlib_import__is_omitted():
    code = "import sys"
    expect = []
    assert set(parse_code(code)) == set(expect)


def test_parse_code__simple_import__extracts_module_name():
    code = "import numpy"
    expect = {ParsedImport("numpy", None)}
    assert set(parse_code(code)) == expect


def test_parse_code__two_stdlib_imports__are_both_omitted():
    code = "import platform, sys"
    expect = []
    assert set(parse_code(code)) == set(expect)


def test_parse_code__one_stdlib_one_external_import__extracts_external_import():
    code = "import sys, pandas"
    expect = {ParsedImport("pandas", None)}
    assert set(parse_code(code)) == expect


def test_parse_code__two_imports__extracts_both_modules():
    code = "import numpy, pandas"
    expect = {ParsedImport("numpy", None), ParsedImport("pandas", None)}
    assert set(parse_code(code)) == expect


def test_parse_code__simple_import_from_stdlib__is_omitted():
    code = "from sys import executable"
    expect = []
    assert set(parse_code(code)) == set(expect)


def test_parse_code__simple_import_from__extracts_module():
    code = "from numpy import array"
    expect = {ParsedImport("numpy", None)}
    assert set(parse_code(code)) == expect


def test_parse_code__import_with_compound_names__extracts_first_component():
    code = dedent(
        """\
        import parent.child
        from foo.bar import baz
        """
    )
    expect = with_location(["parent", "foo"], None)
    assert set(parse_code(code)) == set(expect)


def test_parse_code__relative_imports__are_ignored():
    code = dedent(
        """\
        from . import bar
        from .foo import bar
        from ..foo import bar
        from .foo.bar import baz
        """
    )
    expect = set()
    assert set(parse_code(code)) == expect


def test_parse_code__combo_of_simple_imports__extracts_all_external_imports():
    code = dedent(
        """\
        from pathlib import Path
        import sys
        import unittest as obsolete

        import requests
        from foo import bar, baz
        import numpy as np
        """
    )
    expect = with_location(["requests", "foo", "numpy"], None)
    assert set(parse_code(code)) == set(expect)


def test_parse_file__combo_of_simple_imports__extracts_all_externals(tmp_path):
    code = dedent(
        """\
        from pathlib import Path
        import sys
        import unittest as obsolete

        import requests
        from foo import bar, baz
        import numpy as np
        """
    )
    script = tmp_path / "test.py"
    script.write_text(code)

    expect = with_location(["requests", "foo", "numpy"], tmp_path / "test.py")
    assert set(parse_file(script)) == set(expect)


def test_parse_dir__with_py_and_non_py__extracts_only_from_py_files(tmp_path):
    code1 = dedent(
        """\
        from my_pathlib import Path
        """
    )
    (tmp_path / "test1.py").write_text(code1)

    code2 = dedent(
        """\
        import pandas
        """
    )
    (tmp_path / "test2.py").write_text(code2)

    not_code = dedent(
        """\
        This is not code, even if it contains the
        import word.
        """
    )
    (tmp_path / "not_python.txt").write_text(not_code)

    expect = {
        ParsedImport("my_pathlib", tmp_path / "test1.py"),
        ParsedImport("pandas", tmp_path / "test2.py"),
    }
    assert set(parse_dir(tmp_path)) == expect


def test_parse_dir__imports__are_extracted_in_order_of_encounter(tmp_path):
    first = dedent(
        """\
        import my_sys
        import foo
        """
    )
    (tmp_path / "first.py").write_text(first)

    second = dedent(
        """\
        import my_sys
        import xyzzy
        """
    )
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir/second.py").write_text(second)

    expect = with_location(["my_sys", "foo"], tmp_path / "first.py") + with_location(
        ["my_sys", "xyzzy"], tmp_path / "subdir/second.py"
    )
    assert list(parse_dir(tmp_path)) == expect
