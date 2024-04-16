"""Test that we can extract simple imports from Python code."""

import json
import logging
from io import BytesIO
from pathlib import Path
from textwrap import dedent
from typing import Dict, List, Tuple, Union

import pytest

from fawltydeps.extract_imports import (
    parse_code,
    parse_notebook_file,
    parse_python_file,
    parse_sources,
)
from fawltydeps.types import CodeSource, Location, ParsedImport, PathOrSpecial

from .utils import dedent_bytes


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
            "execution_count": None,
            "metadata": {"id": ""},
            "outputs": [],
            "source": source,
        }

    types = (
        [cell_types] * len(cells_source) if isinstance(cell_types, str) else cell_types
    )

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


@pytest.fixture()
def write_code_sources(write_tmp_files):
    """A wrapper around write_tmp_files() that return CodeSource objects."""

    def _inner(file_contents: Dict[str, str]) -> Tuple[Path, List[CodeSource]]:
        tmp_path = write_tmp_files(file_contents)
        sources = []
        for filepath in file_contents:
            assert filepath.endswith((".py", ".ipynb"))
            sources.append(CodeSource(tmp_path / filepath, tmp_path))
        return tmp_path, sources

    return _inner


@pytest.mark.parametrize(
    ("code", "expected_import_line_pairs"),
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
            "from __future__ import annotations",
            [],
            id="import_from_future__is_omitted",
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
        pytest.param(
            dedent(
                """\
                try:  # Python 3
                    from http.server import HTTPServer, SimpleHTTPRequestHandler
                except ImportError:  # Python 2
                    from BaseHTTPServer import HTTPServer
                    from SimpleHTTPServer import SimpleHTTPRequestHandler
                """
            ),
            [],
            id="stdlib_import_with_ImportError_fallback__ignores_all",
        ),
        pytest.param(
            dedent(
                """\
                if sys.version_info >= (3, 0):
                    from http.server import HTTPServer, SimpleHTTPRequestHandler
                else:
                    from BaseHTTPServer import HTTPServer
                    from SimpleHTTPServer import SimpleHTTPRequestHandler
                """
            ),
            [],
            id="stdlib_import_with_if_else_fallback__ignores_all",
        ),
        pytest.param(
            dedent_bytes(
                b"""\
                # -*- coding: big5 -*-

                # Some Traditional Chinese characters:
                chars = "\xa4@\xa8\xc7\xa4\xa4\xa4\xe5\xa6r\xb2\xc5"

                import numpy
                """
            ),
            [("numpy", 6)],
            id="legacy_encoding__is_correctly_interpreted",
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


def test_parse_python_file__legacy_encoding__extracts_import(tmp_path):
    script = tmp_path / "big5.py"
    script.write_bytes(
        dedent_bytes(
            b"""\
            # -*- coding: big5 -*-

            # Some Traditional Chinese characters:
            chars = "\xa4@\xa8\xc7\xa4\xa4\xa4\xe5\xa6r\xb2\xc5"

            import numpy
            """
        )
    )

    expect = imports_w_linenos([("numpy", 6)], script)
    assert list(parse_python_file(script)) == expect


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
        [["import pandas"], ["import pytorch"]], ["code", "markdown"]
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


def test_parse_notebook_file__with_magic_commands__ignores_magic_commands(
    tmp_path, caplog
):
    exclamation_line = "   ! pip3 install -r 'requirements.txt'\n"
    percent_line = "%pip install numpy\n"

    code = generate_notebook(
        [
            [
                exclamation_line,
                percent_line,
                "import pandas",
            ]
        ]
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 3, 1)], script)

    caplog.set_level(logging.INFO)
    assert set(parse_notebook_file(script)) == set(expect)
    for lineno, line in enumerate([exclamation_line, percent_line], start=1):
        source = Location(script, 1, lineno)
        assert f"Found magic command {line!r} at {source}" in caplog.text


def test_parse_notebook_file__with_magic_commands__ignores__multilines_magic_commands(
    tmp_path, caplog
):
    exclamation_line = "   ! pip3 install -r 'requirements.txt '\\\n"
    continuation_line = " -- pip3 install poetry\n"
    percent_line = "%pip install numpy\n"

    code = generate_notebook(
        [
            [
                exclamation_line,
                continuation_line,
                percent_line,
                "import pandas",
            ]
        ]
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 4, 1)], script)

    caplog.set_level(logging.INFO)
    assert set(parse_notebook_file(script)) == set(expect)
    for lineno, line in [(1, exclamation_line), (3, percent_line)]:
        source = Location(script, 1, lineno)
        assert f"Found magic command {line!r} at {source}" in caplog.text


def test_parse_notebook_file__with_magic_commands__ignores__shell_magic_commands(
    tmp_path, caplog
):
    exclamation_line = "   ! pip3 install -r 'requirements.txt '\\\n"
    continuation_line = "-- verbose"

    code = generate_notebook(
        [
            [
                exclamation_line,
                continuation_line,
                "import pandas",
            ]
        ]
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expect = imports_w_linenos_cellnos([("pandas", 3, 1)], script)

    caplog.set_level(logging.INFO)
    assert set(parse_notebook_file(script)) == set(expect)
    source = Location(script, 1, 1)
    assert f"Found magic command {exclamation_line!r} at {source}" in caplog.text


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


def test_parse_sources__with_py_and_ipynb__extracts_from_all_files(
    write_code_sources,
):
    tmp_path, code_sources = write_code_sources(
        {
            "test1.py": "from my_pathlib import Path",
            "test2.py": "import pandas",
            "test3.ipynb": generate_notebook([["import pytorch"]]),
        }
    )

    expect = {
        ParsedImport("my_pathlib", Location(tmp_path / "test1.py", lineno=1)),
        ParsedImport("pandas", Location(tmp_path / "test2.py", lineno=1)),
        ParsedImport("pytorch", Location(tmp_path / "test3.ipynb", cellno=1, lineno=1)),
    }
    assert set(parse_sources(code_sources)) == expect


def test_parse_sources__imports__are_extracted_in_order_of_encounter(
    write_code_sources,
):
    tmp_path, code_sources = write_code_sources(
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
    assert list(parse_sources(code_sources)) == expect


@pytest.mark.parametrize(
    ("code", "expect_data"),
    [
        pytest.param(
            {
                "my_application.py": "import my_utils",
                "my_utils.py": "import sys",
            },
            [],
            id="__ignore_imports_from_the_same_dir",
        ),
        pytest.param(
            {
                "my_app/__init__.py": "",
                "my_app/main.py": "from my_app import utils",
                "my_app/utils.py": "import numpy",
            },
            [("numpy", "my_app/utils.py", 1)],
            id="__ignore_self_imports",
        ),
        pytest.param(
            {
                "classifier/effnet.py": "from resnet import make_weights_for_balanced_classes",
                "classifier/resnet.py": "make_weights_for_balanced_classes = lambda x:x",
            },
            [],
            id="__ignore_imports_from_the_same_child_dir",
        ),
        pytest.param(
            {
                "dir/classifier/effnet.py": "from resnet import make_weights_for_balanced_classes",
                "dir/classifier/resnet.py": "make_weights_for_balanced_classes = lambda x:x",
            },
            [],
            id="__ignore_imports_from_the_same_nested_dir",
        ),
        pytest.param(
            {
                "detr/main.py": "import util.misc as utils",
                "detr/util/__init__.py": "",
                "detr/util/misc.py": "a = 1",
            },
            [],
            id="__ignore_imports_from_submodule",
        ),
        pytest.param(
            {
                "efficientdet/effdet/data/loader.py": "from effdet.anchors import AnchorLabeler",
                "efficientdet/effdet/data/__init__.py": "",
                "efficientdet/effdet/__init__.py": "",
                "efficientdet/effdet/anchors.py": "class AnchorLabel",
            },
            [],
            id="__ignore_imports_from_uncle",
        ),
    ],
)
def test_parse_sources__ignore_first_party_imports(
    code, expect_data, write_code_sources
):
    tmp_path, code_sources = write_code_sources(code)
    expect = [
        ParsedImport(
            name=e[0],
            source=Location(path=tmp_path / e[1], lineno=e[2]),
        )
        for e in expect_data
    ]

    assert list(parse_sources(code_sources)) == expect


def test_parse_sources__legacy_encoding_on_stdin__extracts_import():
    code = dedent_bytes(
        b"""\
        # -*- coding: big5 -*-

        # Some Traditional Chinese characters:
        chars = "\xa4@\xa8\xc7\xa4\xa4\xa4\xe5\xa6r\xb2\xc5"

        import numpy
        """
    )

    expect = imports_w_linenos([("numpy", 6)], "<stdin>")
    assert list(parse_sources([CodeSource("<stdin>")], BytesIO(code))) == expect
