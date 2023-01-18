"""Test that we can extract simple imports from Python code."""
import json
import logging
from pathlib import Path
from textwrap import dedent
from typing import List, Optional, Tuple, Union

import pytest

from fawltydeps.extract_imports import (
    ParsedImport,
    parse_code,
    parse_dir,
    parse_notebook_file,
    parse_python_file,
)


def imports_w_linenos(
    names_w_linenos: List[Tuple[str, int]],
    path: Optional[Path] = None,
) -> List[ParsedImport]:
    return [ParsedImport(name, path, lineno) for name, lineno in names_w_linenos]


def imports_w_linenos_cellnos(
    names_w_linenos_cellnos: List[Tuple[str, int, int]],
    path: Optional[Path] = None,
) -> List[ParsedImport]:
    return [
        ParsedImport(name, path, lineno, cellno)
        for name, lineno, cellno in names_w_linenos_cellnos
    ]


def generate_notebook(
    cells_source: List[List[str]],
    cell_types: Union[List[str], str] = "code",
    language_name: str = "python",
) -> str:
    """Generate a valid ipynb json string from a list of code cells content."""

    def cell_template(cell_type: str, source: List[str]):
        return {
            "cell_type": cell_type,
            "execution_count": "null",
            "metadata": {"id": ""},
            "outputs": [],
            "source": source,
        }

    if isinstance(cell_types, str):
        types = [cell_types] * len(cells_source)
    else:
        types = cell_types

    notebook = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {"provenance": []},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": language_name},
        },
        "cells": [
            cell_template(cell_type, cell_content)
            for cell_type, cell_content in zip(types, cells_source)
        ],
    }
    return json.dumps(notebook, indent=2)


@pytest.mark.parametrize(
    "code,expected_import_line_pairs",
    [
        pytest.param("", [], id="no_code__has_no_imports"),
        pytest.param(
            "import sys",
            [],
            id="stdlib_import__is_omitted",
        ),
        pytest.param(
            "import numpy",
            [("numpy", 1)],
            id="external_import__extracts_module_name",
        ),
        pytest.param(
            "import platform, sys",
            [],
            id="two_stdlib_imports__are_both_omitted",
        ),
        pytest.param(
            "import sys, pandas",
            [("pandas", 1)],
            id="one_stdlib_one_external_import__extracts_external_import",
        ),
        pytest.param(
            "import numpy, pandas",
            [("numpy", 1), ("pandas", 1)],
            id="two_imports__extracts_both_modules",
        ),
        pytest.param(
            "from sys import executable",
            [],
            id="simple_import_from_stdlib__is_omitted",
        ),
        pytest.param(
            "from numpy import array",
            [("numpy", 1)],
            id="simple_import_from_external__extracts_module",
        ),
        pytest.param(
            dedent(
                """\
                import parent.child
                from foo.bar import baz
                """
            ),
            [("parent", 1), ("foo", 2)],
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
            [("requests", 5), ("foo", 6), ("numpy", 7)],
            id="combo_of_simple_imports__extracts_all_external_imports",
        ),
    ],
)
def test_parse_code(code, expected_import_line_pairs):
    expect = imports_w_linenos(expected_import_line_pairs, None)
    assert list(parse_code(code)) == expect


def test_parse_python_file__combo_of_simple_imports__extracts_all_externals(tmp_path):
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

    expect = imports_w_linenos(
        [("requests", 5), ("foo", 6), ("numpy", 7)], tmp_path / "test.py"
    )
    assert list(parse_python_file(script)) == expect


def test_parse_notebook_file__simple_imports__extracts_all(tmp_path):
    code = generate_notebook([["import pandas\n", "import pytorch"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 1, 0), ("pytorch", 2, 0)], script)
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_notebook_file__two_cells__extracts_all(tmp_path):
    code = generate_notebook([["import pandas"], ["import pytorch"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 1, 0), ("pytorch", 1, 1)], script)
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_notebook_file__two_cells__extracts_from_cell_with_imports(tmp_path):
    code = generate_notebook([["import pandas"], ["print('import pytorch')"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 1, 0)], script)
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_notebook_file__two_cells__extracts_from_code_cell(tmp_path):
    code = generate_notebook(
        [["import pandas"], ["import pytcorch"]], ["code", "markdown"]
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 1, 0)], script)
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_notebook_file__on_non_python_language__logs_skipping_msg_and_returns_no_imports(
    tmp_path, caplog
):
    language_name = "Haskell"
    code = generate_notebook(
        [["import Numeric.Log\n", "import Statistics.Distribution"]],
        language_name=language_name,
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)
    caplog.set_level(logging.INFO)

    assert set(parse_notebook_file(script)) == set()

    assert (
        "FawltyDeps supports parsing Python notebooks. "
        f"Found {language_name} in the notebook's metadata on {script}." in caplog.text
    )


def test_parse_notebook_file__on_no_defined_language__logs_skipping_msg_and_returns_no_imports(
    tmp_path, caplog
):
    code = generate_notebook(
        [["import Numeric.Log\n", "import Statistics.Distribution"]],
        language_name="",
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)
    caplog.set_level(logging.INFO)

    assert set(parse_notebook_file(script)) == set()

    assert (
        f"Skipping the notebook on {script}. "
        "Could not find the programming language name in the notebook's metadata."
        in caplog.text
    )


def test_parse_notebook_file__on_no_defined_language_info__logs_skipping_msg_and_returns_no_imports(
    tmp_path, caplog
):
    code = dedent(
        """\
        {
            "cells": [
            {
                "cell_type": "code",
                "source": [
                    "import pandas"
                ]
            }
            ]
        }
       """
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)
    caplog.set_level(logging.INFO)

    assert set(parse_notebook_file(script)) == set()

    assert (
        f"Skipping the notebook on {script}. "
        "Could not find the programming language name in the notebook's metadata."
        in caplog.text
    )


def test_parse_dir__with_py_ipynb_and_non_py__extracts_only_from_py_and_ipynb_files(
    tmp_path,
):
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

    code3 = generate_notebook([["import pytorch"]])
    (tmp_path / "test3.ipynb").write_text(code3)

    not_code = dedent(
        """\
        This is not code, even if it contains the
        import word.
        """
    )
    (tmp_path / "not_python.txt").write_text(not_code)

    expect = {
        ParsedImport("my_pathlib", tmp_path / "test1.py", 1),
        ParsedImport("pandas", tmp_path / "test2.py", 1),
        ParsedImport("pytorch", tmp_path / "test3.ipynb", 1, 0),
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

    expect = imports_w_linenos(
        [("my_sys", 1), ("foo", 2)], tmp_path / "first.py"
    ) + imports_w_linenos([("my_sys", 1), ("xyzzy", 2)], tmp_path / "subdir/second.py")
    assert list(parse_dir(tmp_path)) == expect


def test_parse_dir__files_in_dot_dirs__are_ignored(write_tmp_files):
    tmp_path = write_tmp_files(
        {
            "test1.py": "import numpy",
            ".venv/test2.py": "import pandas",
        }
    )

    expect = {ParsedImport("numpy", tmp_path / "test1.py", 1)}
    assert set(parse_dir(tmp_path)) == expect
