"""Fixtures for tests"""
from textwrap import dedent

import pytest


@pytest.fixture()
def simple_project(tmp_path):

    first = dedent(
        """\
        pandas
        click
        """
    )
    (tmp_path / "requirements.txt").write_text(first)

    second = dedent(
        """\
        pandas
        tensorflow>=2
        """
    )
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir/requirements.txt").write_text(second)

    (tmp_path / "python_file.py").write_text("django")

    return tmp_path
