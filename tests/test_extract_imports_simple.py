"""Test that we can extract simple imports from Python code."""
import json
from pathlib import Path
from textwrap import dedent
from typing import List, Optional, Union

from fawltydeps.extract_imports import (
    ParsedImport,
    parse_code,
    parse_dir,
    parse_notebook_file,
    parse_python_file,
)


def construct_imports(
    names: List[str],
    locations: Union[List[Optional[Path]], Optional[Path]] = None,
    lines: Union[List[Optional[int]], None] = None,
    cells: Union[List[Optional[int]], None] = None,
) -> List[ParsedImport]:

    if not lines:
        lines = [None for _ in names]

    if not cells:
        cells = [None for _ in names]

    if not locations:
        file_locations = [None for _ in names]
    elif isinstance(locations, Path):
        file_locations = [locations for _ in names]
    else:
        file_locations = locations

    return [
        ParsedImport(name=n, location=f, lineno=l, cellno=c)
        for n, f, l, c in zip(names, file_locations, lines, cells)
    ]


def generate_notebook(cells_content: List[List[str]]) -> str:
    """Generate a valid ipynb json string from a list of code cells content."""

    def cell_template(source: List[str]):
        return {
            "cell_type": "code",
            "execution_count": "null",
            "metadata": {"id": ""},
            "outputs": [],
            "source": source,
        }

    notebook = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {"provenance": []},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
        },
        "cells": [cell_template(cell_content) for cell_content in cells_content],
    }
    return json.dumps(notebook, indent=2)


def test_parse_code__simple_import__extracts_module_name():
    code = "import sys"
    expect = {ParsedImport("sys", lineno=1)}
    assert set(parse_code(code)) == expect


def test_parse_code__two_imports__extracts_both_modules():
    code = "import platform, sys"
    expect = {ParsedImport("platform", lineno=1), ParsedImport("sys", lineno=1)}
    assert set(parse_code(code)) == expect


def test_parse_code__simple_import_from__extracts_module():
    code = "from sys import executable"
    expect = {ParsedImport("sys", lineno=1)}
    assert set(parse_code(code)) == expect


def test_parse_code__import_with_compound_names__extracts_first_component():
    code = dedent(
        """\
        import parent.child
        from foo.bar import baz
        """
    )
    expect = construct_imports(["parent", "foo"], lines=[1, 2])
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


def test_parse_code__combo_of_simple_imports__extracts_all():
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
    expect = construct_imports(
        ["pathlib", "sys", "unittest", "requests", "foo", "numpy"],
        lines=[1, 2, 3, 5, 6, 7],
    )
    assert set(parse_code(code)) == set(expect)


def test_parse_python_file__combo_of_simple_imports__extracts_all(tmp_path):
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

    expect = construct_imports(
        ["pathlib", "sys", "unittest", "requests", "foo", "numpy"],
        script,
        [1, 2, 3, 5, 6, 7],
    )
    assert set(parse_python_file(script)) == set(expect)


def test_parse_notebook_file__simple_imports__extracts_all(tmp_path):
    code = generate_notebook([["import pandas\n", "import pytorch"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = construct_imports(["pandas", "pytorch"], script, [1, 2], [0, 0])
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_notebook_file__two_cells__extracts_all(tmp_path):
    code = generate_notebook([["import pandas"], ["import pytorch"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = construct_imports(["pandas", "pytorch"], script, [1, 1], [0, 1])
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_notebook_file__two_cells__extracts_from_cell_with_imports(tmp_path):
    code = generate_notebook([["import pandas"], ["print('import pytorch')"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = construct_imports(["pandas"], script, [1], [0, 1])
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_notebook_file__two_cells__extracts_from_code_cell(tmp_path):
    code = dedent(
        """\
        {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {
            "provenance": []
            },
            "kernelspec": {
            "name": "python3",
            "display_name": "Python 3"
            },
            "language_info": {
            "name": "python"
            }
        },
        "cells": [
            {
            "cell_type": "code",
            "execution_count": null,
            "metadata": {
                "id": "GCOkrQdSXb0N"
            },
            "outputs": [],
            "source": [
                "import pandas"
            ]
            },
            {
            "cell_type": "markdown",
            "source": [
                "import sys"
            ],
            "metadata": {
                "id": "s8qzZ_p02PGG"
            },
            "execution_count": null,
            "outputs": []
            }
        ]
        }
       """
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = construct_imports(["pandas"], script, [1], [0])
    assert set(parse_notebook_file(script)) == set(expect)


def test_parse_dir__with_py_ipynb_and_non_py__extracts_only_from_py_and_ipynb_files(
    tmp_path,
):
    code1 = dedent(
        """\
        from pathlib import Path
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
        ParsedImport("pathlib", tmp_path / "test1.py", 1),
        ParsedImport("pandas", tmp_path / "test2.py", 1),
        ParsedImport("pytorch", tmp_path / "test3.ipynb", 1, 0),
    }
    assert set(parse_dir(tmp_path)) == expect


def test_parse_dir__imports__are_extracted_in_order_of_encounter(tmp_path):
    first = dedent(
        """\
        import sys
        import foo
        """
    )
    (tmp_path / "first.py").write_text(first)

    second = dedent(
        """\
        import sys
        import xyzzy
        """
    )
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir/second.py").write_text(second)

    expect = construct_imports(
        ["sys", "foo"], tmp_path / "first.py", [1, 2]
    ) + construct_imports(["sys", "xyzzy"], tmp_path / "subdir/second.py", [1, 2])
    assert list(parse_dir(tmp_path)) == expect
