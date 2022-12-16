"""Verify graceful failure when we cannot extract imports from Python code."""

from textwrap import dedent

import pytest

from fawltydeps.extract_imports import parse_code, parse_dir, parse_file


def test_parse_code_failures_propagates_SyntaxError():
    code = "This is not Python code\n"
    with pytest.raises(SyntaxError):
        list(parse_code(code))


def test_parse_file_failures_contain_filename(tmp_path):
    code = "This is not Python code\n"
    script = tmp_path / "test.py"
    script.write_text(code)

    with pytest.raises(SyntaxError) as exc_info:
        list(parse_file(script))
    assert exc_info.value.filename == str(script)


def test_parse_dir_with_syntax_error_contains_filename(tmp_path):
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
