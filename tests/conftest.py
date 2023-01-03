"""Fixtures for tests"""
from pathlib import Path
from textwrap import dedent
from typing import Dict

import pytest


@pytest.fixture()
def write_tmp_files(tmp_path: Path):
    def _inner(file_contents: Dict[str, str]) -> Path:
        for filename, contents in file_contents.items():
            path = tmp_path / filename
            assert path.is_relative_to(tmp_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(dedent(contents))
        return tmp_path

    return _inner


@pytest.fixture()
def project_with_requirements(write_tmp_files):
    return write_tmp_files(
        {
            "requirements.txt": """\
                pandas
                click
                """,
            "subdir/requirements.txt": """\
                pandas
                tensorflow>=2
                """,
            "python_file.py": "import django",
        }
    )


@pytest.fixture()
def project_with_setup_and_requirements(write_tmp_files):
    return write_tmp_files(
        {
            "requirements.txt": """\
                pandas
                click
                """,
            "subdir/requirements.txt": """\
                pandas
                tensorflow>=2
                """,
            "setup.py": """\
                from setuptools import setup

                setup(
                    name="MyLib",
                    install_requires=["pandas", "click>=1.2"],
                    extras_require={
                        'annoy': ['annoy==1.15.2'],
                        'chinese': ['jieba']
                        }
                )
                """,
            "python_file.py": "import django",
        }
    )
