"""Test that we can extract simple imports from Python code."""

from pathlib import Path
from textwrap import dedent
from typing import List, Optional

from fawltydeps.extract_imports import (
    ParsedImport,
    parse_code,
    parse_dir,
    parse_file,
    parse_notebook,
)


def with_location_and_line(
    imports: List[str], location: Optional[Path], lines: List[Optional[int]]
) -> List[ParsedImport]:
    return [
        ParsedImport(name=i, location=location, lineno=j)
        for i, j in zip(imports, lines)
    ]


def generate_notebook(cells_content: List[List[str]]) -> str:
    """Generate a valid ipynb json string from a list of code cells content."""
    notebook_template = dedent(
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
            %s
        ]
        }
        """
    )
    cell_template = dedent(
        """
        {
            "cell_type": "code",
            "execution_count": null,
            "metadata": {
                "id": "GCOkrQdSXb0N"
            },
            "outputs": [],
            "source": [
                %s
            ]
            }
        """
    )
    cells = [
        cell_template
        % ",".join(
            f'"{line}"'.encode("unicode_escape").decode() for line in cell_content
        )
        for cell_content in cells_content
    ]

    return notebook_template % ",\n".join(cells)


def test_parse_code__simple_import__extracts_module_name():
    code = "import sys"
    expect = {ParsedImport("sys", None, 1)}
    assert set(parse_code(code)) == expect


def test_parse_code__two_imports__extracts_both_modules():
    code = "import platform, sys"
    expect = {ParsedImport("platform", None, 1), ParsedImport("sys", None, 1)}
    assert set(parse_code(code)) == expect


def test_parse_code__simple_import_from__extracts_module():
    code = "from sys import executable"
    expect = {ParsedImport("sys", None, 1)}
    assert set(parse_code(code)) == expect


def test_parse_code__import_with_compound_names__extracts_first_component():
    code = dedent(
        """\
        import parent.child
        from foo.bar import baz
        """
    )
    expect = with_location_and_line(["parent", "foo"], None, [1, 2])
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
    expect = with_location_and_line(
        ["pathlib", "sys", "unittest", "requests", "foo", "numpy"],
        None,
        [1, 2, 3, 5, 6, 7],
    )
    assert set(parse_code(code)) == set(expect)


def test_parse_file__combo_of_simple_imports__extracts_all(tmp_path):
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

    expect = with_location_and_line(
        ["pathlib", "sys", "unittest", "requests", "foo", "numpy"],
        tmp_path / "test.py",
        [1, 2, 3, 5, 6, 7],
    )
    assert set(parse_file(script)) == set(expect)


def test_parse_notebook__simple_imports__extracts_all(tmp_path):
    code = generate_notebook([["import pandas\n", "import pytorch"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = with_location_and_line(["pandas", "pytorch"], script, [1, 2])
    assert set(parse_notebook(script)) == set(expect)


def test_parse_notebook__two_cells__extracts_all(tmp_path):
    code = generate_notebook([["import pandas"], ["import pytorch"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = with_location_and_line(["pandas", "pytorch"], script, [1, 1])
    assert set(parse_notebook(script)) == set(expect)


def test_parse_notebook__two_cells__extracts_from_cell_with_imports(tmp_path):
    code = generate_notebook([["import pandas"], ["print('import pytorch')"]])
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = with_location_and_line(["pandas"], script, [1])
    assert set(parse_notebook(script)) == set(expect)


def test_parse_notebook__two_cells__extracts_from_code_cell(tmp_path):
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

    expect = with_location_and_line(["pandas"], script, [1])
    assert set(parse_notebook(script)) == set(expect)


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
        ParsedImport("pytorch", tmp_path / "test3.ipynb", 1),
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

    expect = with_location_and_line(
        ["sys", "foo"], tmp_path / "first.py", [1, 2]
    ) + with_location_and_line(["sys", "xyzzy"], tmp_path / "subdir/second.py", [1, 2])
    assert list(parse_dir(tmp_path)) == expect
