"""Verify behavior of command-line interface.

This is more of an integration test than a unit test, in that we test the
overall behavior of the command line interface, rather than testing our
core exhaustively (which is what the other unit tests are for.
"""

import subprocess
from pathlib import Path
from textwrap import dedent
from typing import Iterable, Optional, Tuple

import pytest

from .test_extract_imports_simple import generate_notebook


@pytest.fixture
def project_with_code_and_requirements_txt(write_tmp_files):
    def _inner(*, imports: Iterable[str], declares: Iterable[str]):
        code = "".join(f"import {s}\n" for s in imports)
        requirements = "".join(f"{s}\n" for s in declares)
        return write_tmp_files(
            {
                "code.py": code,
                "requirements.txt": requirements,
            }
        )

    return _inner


def run_fawltydeps(
    *args: str,
    to_stdin: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Tuple[str, str, int]:
    proc = subprocess.run(
        ["fawltydeps"] + list(args),
        input=to_stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        cwd=cwd,
    )
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


def test_list_imports__from_dash__prints_imports_from_stdin():
    code = dedent(
        """\
        from pathlib import Path
        import platform, sys

        import requests
        from foo import bar, baz
        import numpy as np
        """
    )

    expect = [
        f"{i}: <stdin>:{n}" for i, n in [("requests", 4), ("foo", 5), ("numpy", 6)]
    ]
    output, errors, returncode = run_fawltydeps(
        "--list-imports", "--code=-", to_stdin=code
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 0


def test_list_imports__from_py_file__prints_imports_from_file(write_tmp_files):
    tmp_path = write_tmp_files(
        {
            "myfile.py": """\
                from pathlib import Path
                import platform, sys

                import requests
                from foo import bar, baz
                import numpy as np
                """,
        }
    )

    expect = ["requests", "foo", "numpy"]
    output, errors, returncode = run_fawltydeps(
        "--list-imports", f"--code={tmp_path}/myfile.py"
    )
    found_imports = [line.split(":", 1)[0] for line in output.splitlines()]
    assert found_imports == expect
    assert errors == ""
    assert returncode == 0


def test_list_imports__from_ipynb_file__prints_imports_from_file(write_tmp_files):
    tmp_path = write_tmp_files(
        {
            "myfile.ipynb": generate_notebook([["import pytorch"]]),
        }
    )

    expect = ["pytorch"]
    output, errors, returncode = run_fawltydeps(
        "--list-imports", f"--code={tmp_path}/myfile.ipynb"
    )
    found_imports = [line.split(":", 1)[0] for line in output.splitlines()]
    assert found_imports == expect
    assert errors == ""
    assert returncode == 0


def test_list_imports__from_dir__prints_imports_from_py_and_ipynb_files_only(
    write_tmp_files,
):
    notebook_content = generate_notebook([["import pytorch"]])
    tmp_path = write_tmp_files(
        {
            "file1.py": """\
                from my_pathlib import Path
                import pandas, scipy
                """,
            "file2.NOT_PYTHON": """\
                import requests
                from foo import bar, baz
                import numpy as np
                """,
            "file3.ipynb": notebook_content,
        }
    )

    expect = ["my_pathlib", "pandas", "scipy", "pytorch"]
    output, errors, returncode = run_fawltydeps("--list-imports", f"--code={tmp_path}")
    found_imports = [line.split(":", 1)[0] for line in output.splitlines()]
    assert found_imports == expect
    assert errors == ""
    assert returncode == 0


def test_list_imports__from_non_supported_file_format__fails_with_exit_code_2(tmp_path):
    filepath = tmp_path / "test.NOT_SUPPORTED"
    filepath.write_text("import pandas")
    _output, errors, returncode = run_fawltydeps("--list-imports", f"--code={filepath}")
    assert (
        f"Cannot parse code from {filepath}: supported formats are .py and .ipynb."
        in errors
    )
    assert returncode == 2


def test_list_imports__from_missing_file__fails_with_exit_code_2(tmp_path):
    filepath = tmp_path / "MISSING.py"
    _output, errors, returncode = run_fawltydeps("--list-imports", f"--code={filepath}")
    assert f"Cannot parse code from {filepath}: Not a dir or file!" in errors
    assert returncode == 2


def test_list_imports__from_empty_dir__logs_but_extracts_nothing(tmp_path):
    # Enable log level INFO with -v
    output, errors, returncode = run_fawltydeps(
        "--list-imports", f"--code={tmp_path}", "-v"
    )
    assert output == ""
    assert f"Parsing Python files under {tmp_path}" in errors
    assert returncode == 0


def test_list_deps__dir__prints_deps_from_requirements_txt(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests", "pandas"],
        declares=["requests", "pandas"],
    )

    expect = [
        f"pandas: {tmp_path}/requirements.txt",
        f"requests: {tmp_path}/requirements.txt",
    ]
    output, errors, returncode = run_fawltydeps("--list-deps", f"--deps={tmp_path}")
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 0


# TODO: The following tests need changes inside extract_dependencies


def TODO_test_list_deps__missing_dir__fails_with_exit_code_2(tmp_path):
    _, _, returncode = run_fawltydeps("--list-deps", f"--deps={tmp_path}/MISSING_DIR")
    assert returncode == 2


def TODO_test_list_deps__empty_dir__verbosely_logs_but_extracts_nothing(tmp_path):
    # Enable log level INFO with -v
    output, errors, returncode = run_fawltydeps(
        "--list-deps", f"--deps={tmp_path}", "-v"
    )
    assert output == ""
    assert f"Extracting dependencies from {tmp_path}" in errors
    assert returncode == 0


def test_check__simple_project_imports_match_dependencies__prints_nothing(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests", "pandas"],
        declares=["requests", "pandas"],
    )

    expect = []
    output, errors, returncode = run_fawltydeps(
        "--check", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 0


def test_check__simple_project_with_missing_deps__reports_undeclared(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests", "pandas"],
        declares=["pandas"],
    )

    expect = [
        "These imports appear to be undeclared dependencies:",
        "- 'requests' imported at:",
        f"    {str(tmp_path / 'code.py')}:1",
    ]
    output, errors, returncode = run_fawltydeps(
        "--check", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 3


def test_check__simple_project_with_extra_deps__reports_unused(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests"],
        declares=["requests", "pandas"],
    )

    expect = [
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas' declared in:",
        f"    {tmp_path / 'requirements.txt'}",
    ]
    output, errors, returncode = run_fawltydeps(
        "--check", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 4


def test_check__simple_project__can_report_both_undeclared_and_unused(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests"],
        declares=["pandas"],
    )

    expect = [
        "These imports appear to be undeclared dependencies:",
        "- 'requests' imported at:",
        f"    {tmp_path / 'code.py'}:1",
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas' declared in:",
        f"    {tmp_path / 'requirements.txt'}",
    ]
    output, errors, returncode = run_fawltydeps(
        "--check", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 3  # undeclared is more important than unused


def test_check_undeclared__simple_project__reports_only_undeclared(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests"],
        declares=["pandas"],
    )

    expect = [
        "These imports appear to be undeclared dependencies:",
        "- 'requests' imported at:",
        f"    {str(tmp_path / 'code.py')}:1",
    ]
    output, errors, returncode = run_fawltydeps(
        "--check-undeclared", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 3


def test_check_unused__simple_project__reports_only_unused(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests"],
        declares=["pandas"],
    )

    expect = [
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas' declared in:",
        f"    {tmp_path / 'requirements.txt'}",
    ]
    output, errors, returncode = run_fawltydeps(
        "--check-unused", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 4


def test__no_action__defaults_to_check_action(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests"],
        declares=["pandas"],
    )

    expect = [
        "These imports appear to be undeclared dependencies:",
        "- 'requests' imported at:",
        f"    {tmp_path / 'code.py'}:1",
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas' declared in:",
        f"    {tmp_path / 'requirements.txt'}",
    ]
    output, errors, returncode = run_fawltydeps(
        f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 3


def test__no_options__defaults_to_check_action_in_current_dir(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests"],
        declares=["pandas"],
    )

    expect = [
        "These imports appear to be undeclared dependencies:",
        "- 'requests' imported at:",
        f"    {str(tmp_path / 'code.py')}:1",
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas' declared in:",
        f"    {tmp_path / 'requirements.txt'}",
    ]
    output, errors, returncode = run_fawltydeps(cwd=tmp_path)
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 3
