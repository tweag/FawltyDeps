"""Verify graceful failure when we cannot extract imports from Python code."""

import logging
from textwrap import dedent

from fawltydeps.extract_imports import (
    parse_code,
    parse_dir,
    parse_notebook_file,
    parse_python_file,
)
from fawltydeps.types import Location, ParsedImport


def test_parse_notebook_file__on_invalid_json__logs_error(tmp_path, caplog):
    code = dedent(
        """\
        {
            "cells": [
            {"cell_type": "code",
            }
        }
       """
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)
    expected = []
    caplog.set_level(logging.ERROR)
    assert list(parse_notebook_file(script)) == expected
    assert f"Could not parse code from {script}" in caplog.text


def test_parse_notebook_file__on_parse_error_one_cell__logs_error_and_continues(
    tmp_path, caplog
):
    code = dedent(
        """\
        {
            "metadata": {
                "language_info": {
                    "name": "Python"
                }
            },
            "cells": [
            {
                "cell_type": "code"
            },
            {
                "cell_type": "code",
                "source": ["import pandas"]
            }
        ]
        }
       """
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    expected = [ParsedImport("pandas", Location(script, lineno=1, cellno=2))]
    caplog.set_level(logging.ERROR)
    assert list(parse_notebook_file(script)) == expected
    assert f"Could not parse code from {script}[1]" in caplog.text


def test_parse_code__on_parse_error__logs_error(caplog):
    code = dedent(
        """
        import pandas
        This is not Python code
        """
    )
    source = Location("<stdin>")
    expect = []
    caplog.set_level(logging.ERROR)
    assert list(parse_code(code, source=source)) == expect
    assert f"Could not parse code from {source}" in caplog.text


def test_parse_file__on_syntax_error__logs_error(tmp_path, caplog):
    code = "This is not Python code\n"
    script = tmp_path / "test.py"
    script.write_text(code)

    expect = []
    caplog.set_level(logging.ERROR)
    assert list(parse_python_file(script)) == expect
    assert f"Could not parse code from {script}" in caplog.text


def test_parse_dir__on_parse_error__error_log_contains_filename(tmp_path, caplog):
    code = dedent(
        """\
        This file is littered with Python syntax errors...
        import word.
        """
    )
    script = tmp_path / "python_with_syntax_error.py"
    script.write_text(code)

    expect = []
    caplog.set_level(logging.ERROR)
    assert list(parse_dir(tmp_path)) == expect
    assert f"Could not parse code from {script}" in caplog.text


def test_parse_notebook_file__on_invalid_python_one_cell__logs_error_and_continues(
    tmp_path, caplog
):
    code = dedent(
        """\
        {
            "metadata": {
                "language_info": {
                    "name": "Python"
                }
            },
            "cells": [
            {
                "cell_type": "code",
                "source": [
                    "import json..."
                ]
            },
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

    caplog.set_level(logging.ERROR)
    assert list(parse_notebook_file(script)) == [
        ParsedImport("pandas", Location(script, lineno=1, cellno=2))
    ]
    assert f"Could not parse code from {script}[1]" in caplog.text
