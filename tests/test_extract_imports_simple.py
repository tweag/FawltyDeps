"""Test that we can extract simple imports from Python code."""
import json
import logging
from textwrap import dedent
from typing import List, Tuple, Union

import pytest

from fawltydeps.extract_imports import (
    parse_code,
    parse_dir,
    parse_notebook_file,
    parse_python_file,
)
from fawltydeps.types import Location, ParsedImport, PathOrSpecial


def imports_w_linenos(
    names_w_linenos: List[Tuple[str, int]],
    path: PathOrSpecial = "<stdin>",
) -> List[ParsedImport]:
    return [
        ParsedImport(name, Location(path, lineno=lineno))
        for name, lineno in names_w_linenos
    ]


def imports_w_linenos_cellnos(
    names_w_linenos_cellnos: List[Tuple[str, int, int]],
    path: PathOrSpecial = "<stdin>",
) -> List[ParsedImport]:
    return [
        ParsedImport(name, Location(path, cellno=cellno, lineno=lineno))
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
    expect = imports_w_linenos(expected_import_line_pairs, "<stdin>")
    assert list(parse_code(code, source=Location("<stdin>"))) == expect


def test_parse_python_file__combo_of_simple_imports__extracts_all_externals(
    write_tmp_files,
):
    tmp_path = write_tmp_files(
        {
            "test.py": """\
                from pathlib import Path
                import sys
                import unittest as obsolete

                import requests
                from foo import bar, baz
                import numpy as np
                """,
        }
    )

    expect = imports_w_linenos(
        [("requests", 5), ("foo", 6), ("numpy", 7)], tmp_path / "test.py"
    )
    assert list(parse_python_file(tmp_path / "test.py")) == expect


def test_parse_notebook_file__simple_imports__extracts_all(tmp_path):
    code = generate_notebook([["import pandas\n", "import pytorch"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 1, 1), ("pytorch", 2, 1)], script)
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_notebook_file__two_cells__extracts_all(tmp_path):
    code = generate_notebook([["import pandas"], ["import pytorch"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 1, 1), ("pytorch", 1, 2)], script)
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_notebook_file__two_cells__extracts_from_cell_with_imports(tmp_path):
    code = generate_notebook([["import pandas"], ["print('import pytorch')"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 1, 1)], script)
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_notebook_file__two_cells__extracts_from_code_cell(tmp_path):
    code = generate_notebook(
        [["import pandas"], ["import pytcorch"]], ["code", "markdown"]
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 1, 1)], script)
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


def test_parse_notebook_file__with_magic_commands__ignores_magic_commands(tmp_path):
    code = generate_notebook(
        [
            [
                "   ! pip3 install -r 'requirements.txt'\n",
                "% pip install numpy\n",
                "import pandas",
            ]
        ]
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 3, 1)], script)
    assert set(parse_notebook_file(script)) == set(expect)


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
    write_tmp_files,
):
    tmp_path = write_tmp_files(
        {
            "test1.py": "from my_pathlib import Path",
            "test2.py": "import pandas",
            "test3.ipynb": generate_notebook([["import pytorch"]]),
            "not_python.txt": """\
                This is not code, even if it contains the
                import word.
                """,
        }
    )

    expect = {
        ParsedImport("my_pathlib", Location(tmp_path / "test1.py", lineno=1)),
        ParsedImport("pandas", Location(tmp_path / "test2.py", lineno=1)),
        ParsedImport("pytorch", Location(tmp_path / "test3.ipynb", cellno=1, lineno=1)),
    }
    assert set(parse_dir(tmp_path)) == expect


def test_parse_dir__imports__are_extracted_in_order_of_encounter(write_tmp_files):
    tmp_path = write_tmp_files(
        {
            "first.py": """\
                import my_sys
                import foo
                """,
            "subdir/second.py": """\
                import my_sys
                import xyzzy
                """,
        }
    )

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

    expect = {ParsedImport("numpy", Location(tmp_path / "test1.py", lineno=1))}
    assert set(parse_dir(tmp_path)) == expect
