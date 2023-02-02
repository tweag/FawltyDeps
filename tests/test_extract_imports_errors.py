"""Verify graceful failure when we cannot extract imports from Python code."""

import json
from textwrap import dedent

import pytest

from fawltydeps.extract_imports import (
    parse_code,
    parse_dir,
    parse_notebook_file,
    parse_python_file,
)
from fawltydeps.types import Location, ParsedImport


def test_parse_notebook_file__on_parse_error__propagates_SyntaxError(tmp_path):
    code = dedent(
        """\
        {
            "metadata": {
                "language_info": {
                    "name": "Python"
                }
            },
            "cells": [
            {"cell_type": "code"
            }
        ]
        }
       """
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    with pytest.raises(SyntaxError):
        list(parse_notebook_file(script))


def test_parse_notebook_file__on_parse_error__SyntaxError_raised_with_msg(tmp_path):
    code = dedent(
        """\
        {
            "metadata": {
                "language_info": {
                    "name": "Python"
                }
            },
            "cells": [
            {"cell_type": "code"
            }
        ]
        }
       """
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    with pytest.raises(SyntaxError) as exc_info:
        list(parse_notebook_file(script))
    assert exc_info.value.msg == f"Cannot parse code from {script}[1]."


def test_parse_notebook_file__on_invalid_json__JSONDecodeError_raised_with_msg(
    tmp_path,
):
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

    with pytest.raises(json.decoder.JSONDecodeError):
        list(parse_notebook_file(script))


def test_parse_code__on_parse_error__logs_error(caplog):
    code = dedent(
        """
        import pandas
        This is not Python code
        """
    )
    source = Location("<stdin>")
    expect = []
    assert list(parse_code(code, source=source)) == expect
    assert f"Could not parse code from {source}" in caplog.text


def test_parse_file__on_syntax_error__logs_error(tmp_path, caplog):
    code = "This is not Python code\n"
    script = tmp_path / "test.py"
    script.write_text(code)

    expect = []
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

    assert list(parse_notebook_file(script)) == [
        ParsedImport("pandas", Location(script, lineno=1, cellno=2))
    ]
    assert f"Could not parse code from {script}[1]" in caplog.text
