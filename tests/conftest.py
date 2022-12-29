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

    (tmp_path / "python_file.py").write_text("import django")

    return tmp_path


@pytest.fixture()
def project_with_setup_requirements(tmp_path):

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

    setup = dedent(
        """\
                from setuptools import setup

                setup(
                    name="MyLib",
                    install_requires=["pandas", "click>=1.2"],
                    extras_require={
                        'annoy': ['annoy==1.15.2'],
                        'chinese': ['jieba']
                        }
                )
        """
    )
    (tmp_path / "setup.py").write_text(setup)

    (tmp_path / "python_file.py").write_text("import django")

    return tmp_path
