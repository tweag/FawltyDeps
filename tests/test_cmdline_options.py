from hypothesis import given
import hypothesis.strategies as st
import pytest
from tests.test_cmdline import run_fawltydeps
from itertools import product


@pytest.fixture
def project_without_errors(write_tmp_files):
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
            # This file should be ignored:
            ".venv/requirements.txt": """\
                foo_package
                bar_package
                """,
            "python_file.py": "import pandas as pd \nimport click\nimport  tensorflow",
        }
    )


actions = [
    None,
    "--check",
    "--check-undeclared",
    "--check-unused",
    "--list-imports",
    "--list-deps",
]
output_formats = [None, "--summary", "--detailed", "--json"]


@pytest.mark.parametrize("action,output_format", product(actions, output_formats))
def test_options_interactions__correct_options__give_success_code(
    action,
    output_format,
    project_without_errors,
):
    """Check if a combination of valid options

    makes a valid run of fawltydeps CLI tool.
    """

    args = [f"{project_without_errors}"]
    if action is not None:
        args.append(action)
    if output_format is not None:
        args.append(output_format)

    output, errors, returncode = run_fawltydeps(*args)
    assert returncode == 0
