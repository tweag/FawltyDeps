"""Test that we can extract simple imports from Python code."""

from pathlib import Path
from textwrap import dedent
from typing import List, Optional

import pytest

from fawltydeps.extract_imports import ParsedImport, parse_code, parse_dir, parse_file


def with_location(imports: List[str], location: Optional[Path]) -> List[ParsedImport]:
    return [ParsedImport(i, location) for i in imports]


@pytest.mark.parametrize(
    "code,expect",
    [
        pytest.param("", [], id="no_code__has_no_imports"),
        pytest.param(
            "import sys",
            [],
            id="stdlib_import__is_omitted",
        ),
        pytest.param(
            "import numpy",
            ["numpy"],
            id="external_import__extracts_module_name",
        ),
        pytest.param(
            "import platform, sys",
            [],
            id="two_stdlib_imports__are_both_omitted",
        ),
        pytest.param(
            "import sys, pandas",
            ["pandas"],
            id="one_stdlib_one_external_import__extracts_external_import",
        ),
        pytest.param(
            "import numpy, pandas",
            ["numpy", "pandas"],
            id="two_imports__extracts_both_modules",
        ),
        pytest.param(
            "from sys import executable",
            [],
            id="simple_import_from_stdlib__is_omitted",
        ),
        pytest.param(
            "from numpy import array",
            ["numpy"],
            id="simple_import_from_external__extracts_module",
        ),
        pytest.param(
            dedent(
                """\
                import parent.child
                from foo.bar import baz
                """
            ),
            ["parent", "foo"],
            id="import_with_compound_names__extracts_first_component",
        ),
        pytest.param(
            dedent(
                """\
                from . import bar
                from .foo import bar
                from ..foo import bar
                from .foo.bar import baz
                """
            ),
            [],
            id="relative_imports__are_omitted",
        ),
        pytest.param(
            dedent(
                """\
                from pathlib import Path
                import sys
                import unittest as obsolete

                import requests
                from foo import bar, baz
                import numpy as np
                """
            ),
            ["requests", "foo", "numpy"],
            id="combo_of_simple_imports__extracts_all_external_imports",
        ),
    ],
)
def test_parse_code(code, expect):
    assert set(parse_code(code)) == set(with_location(expect, None))


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
