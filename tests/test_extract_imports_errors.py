"""Verify graceful failure when we cannot extract imports from Python code."""

from textwrap import dedent

import pytest

from fawltydeps.extract_imports import (
    parse_code,
    parse_dir,
    parse_python_file,
    parse_notebook_file,
)


def test_parse_code__on_parse_error__propagates_SyntaxError():
    code = "This is not Python code\n"
    with pytest.raises(SyntaxError):
        list(parse_code(code))


def test_parse_python_file__on_parse_error__SyntaxError_contains_filename(tmp_path):
    code = "This is not Python code\n"
    script = tmp_path / "test.py"
    script.write_text(code)

    with pytest.raises(SyntaxError) as exc_info:
        list(parse_python_file(script))
    assert exc_info.value.filename == str(script)


def test_parse_dir__on_parse_error__SyntaxError_contains_filename(tmp_path):
    code = dedent(
        """\
        This file is littered with Python syntax errors...
        import word.
        """
    )
    script = tmp_path / "python_with_syntax_error.py"
    script.write_text(code)

    with pytest.raises(SyntaxError) as exc_info:
        list(parse_dir(tmp_path))
    assert exc_info.value.filename == str(script)


def test_parse_notebook_file__on_parse_error__propagates_SyntaxError(tmp_path):
    code = dedent(
        """\
        {
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
    assert exc_info.value.msg == f"Cannot parse code from {script}: cell 0."


def test_parse_notebook_file__on_invalid_python__SyntaxError_raised_with_msg(tmp_path):
    code = dedent(
        """\
        {
            "cells": [
            {"cell_type": "code",
            "source": [
                "import json..."
            ]
            }
        ]
        }
       """
    )
    script = tmp_path / "test.ipynb"
    script.write_text(code)

    with pytest.raises(SyntaxError) as exc_info:
        list(parse_notebook_file(script))
    assert exc_info.value.msg == f"Cannot parse code from {script}: cell 0."
