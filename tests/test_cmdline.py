"""Verify behavior of command-line interface.

This is more of an integration test than a unit test, in that we test the
overall behavior of the command line interface, rather than testing our
core exhaustively (which is what the other unit tests are for.
"""

import json
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


def test_list_imports__verbose_from_dash__prints_imports_from_stdin():
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
        f"<stdin>:{n}: {i}" for i, n in [("requests", 4), ("foo", 5), ("numpy", 6)]
    ]
    expect_logs = (
        "INFO:fawltydeps.extract_imports:Parsing Python code from standard input"
    )
    output, errors, returncode = run_fawltydeps(
        "--list-imports", "-v", "--code=-", to_stdin=code
    )
    assert output.splitlines() == expect
    assert errors == expect_logs
    assert returncode == 0


def test_list_imports_quiet__from_dash__prints_imports_from_stdin():
    code = dedent(
        """\
        from pathlib import Path
        import platform, sys

        import requests
        from foo import bar, baz
        import numpy as np
        """
    )

    expect = ["foo", "numpy", "requests"]  # alphabetically sorted
    output, errors, returncode = run_fawltydeps(
        "--list-imports", "--code=-", to_stdin=code
    )
    assert output.splitlines()[:-2] == expect
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

    expect = [
        f"{tmp_path}/myfile.py:{n}: {i}"
        for i, n in [("requests", 4), ("foo", 5), ("numpy", 6)]
    ]
    expect_logs = (
        f"INFO:fawltydeps.extract_imports:Parsing Python file {tmp_path}/myfile.py"
    )
    output, errors, returncode = run_fawltydeps(
        "--list-imports", "-v", f"--code={tmp_path}/myfile.py"
    )
    assert output.splitlines() == expect
    assert errors == expect_logs
    assert returncode == 0


def test_list_imports_json__from_py_file__prints_imports_from_file(write_tmp_files):
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

    expect = {
        "imports": [
            {
                "name": "requests",
                "source": {"path": f"{tmp_path}/myfile.py", "lineno": 4},
            },
            {"name": "foo", "source": {"path": f"{tmp_path}/myfile.py", "lineno": 5}},
            {"name": "numpy", "source": {"path": f"{tmp_path}/myfile.py", "lineno": 6}},
        ],
        "declared_deps": None,
        "undeclared_deps": None,
        "unused_deps": None,
    }
    output, _errors, returncode = run_fawltydeps(
        "--list-imports", "--json", f"--code={tmp_path}/myfile.py"
    )
    assert json.loads(output) == expect
    assert returncode == 0


def test_list_imports__from_ipynb_file__prints_imports_from_file(write_tmp_files):
    tmp_path = write_tmp_files(
        {
            "myfile.ipynb": generate_notebook([["import pytorch"]]),
        }
    )

    expect = [f"{tmp_path}/myfile.ipynb[1]:1: pytorch"]
    expect_logs = (
        f"INFO:fawltydeps.extract_imports:Parsing Notebook file {tmp_path}/myfile.ipynb"
    )
    output, errors, returncode = run_fawltydeps(
        "--list-imports", "-v", f"--code={tmp_path}/myfile.ipynb"
    )
    assert output.splitlines() == expect
    assert errors == expect_logs
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

    expect = [
        f"{tmp_path}/file1.py:{n}: {i}"
        for i, n in [("my_pathlib", 1), ("pandas", 2), ("scipy", 2)]
    ] + [f"{tmp_path}/file3.ipynb[1]:1: pytorch"]
    expect_logs = (
        f"INFO:fawltydeps.extract_imports:Parsing Python files under {tmp_path}"
    )
    output, errors, returncode = run_fawltydeps(
        "--list-imports", "-v", f"--code={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == expect_logs
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
        f"{tmp_path}/requirements.txt: pandas",
        f"{tmp_path}/requirements.txt: requests",
    ]
    output, errors, returncode = run_fawltydeps(
        "--list-deps", "-v", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 0


def test_list_deps_json__dir__prints_deps_from_requirements_txt(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests", "pandas"],
        declares=["requests", "pandas"],
    )

    expect = {
        "imports": None,
        "declared_deps": [
            {"name": "requests", "source": {"path": f"{tmp_path}/requirements.txt"}},
            {"name": "pandas", "source": {"path": f"{tmp_path}/requirements.txt"}},
        ],
        "undeclared_deps": None,
        "unused_deps": None,
    }
    output, _errors, returncode = run_fawltydeps(
        "--list-deps", "--json", f"--deps={tmp_path}"
    )
    assert json.loads(output) == expect
    assert returncode == 0


def test_list_deps_quiet__dir__prints_deps_from_requirements_txt(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests", "pandas"],
        declares=["requests", "pandas"],
    )

    expect = ["pandas", "requests"]
    output, errors, returncode = run_fawltydeps("--list-deps", f"--deps={tmp_path}")
    assert output.splitlines()[:-2] == expect
    assert errors == ""
    assert returncode == 0


# TODO: The following tests need changes inside extract_declared_dependencies


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


def test_check__simple_project_imports_match_dependencies__prints_verbose_option(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests", "pandas"],
        declares=["requests", "pandas"],
    )

    expect = ["For a more verbose report re-run with the `-v` option."]
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
    expect_logs = (
        f"INFO:fawltydeps.extract_imports:Parsing Python files under {tmp_path}"
    )
    output, errors, returncode = run_fawltydeps(
        "--check", "-v", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == expect_logs
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
    expect_logs = (
        f"INFO:fawltydeps.extract_imports:Parsing Python files under {tmp_path}"
    )
    output, errors, returncode = run_fawltydeps(
        "--check", "-v", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == expect_logs
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
    expect_logs = (
        f"INFO:fawltydeps.extract_imports:Parsing Python files under {tmp_path}"
    )
    output, errors, returncode = run_fawltydeps(
        "--check", "-v", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == expect_logs
    assert returncode == 3  # undeclared is more important than unused


def test_check_json__simple_project__can_report_both_undeclared_and_unused(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests"],
        declares=["pandas"],
    )

    expect = {
        "imports": [
            {
                "name": "requests",
                "source": {"path": f"{tmp_path}/code.py", "lineno": 1},
            },
        ],
        "declared_deps": [
            {"name": "pandas", "source": {"path": f"{tmp_path}/requirements.txt"}},
        ],
        "undeclared_deps": [
            {
                "name": "requests",
                "references": [
                    {
                        "name": "requests",
                        "source": {"path": f"{tmp_path}/code.py", "lineno": 1},
                    },
                ],
            },
        ],
        "unused_deps": [
            {
                "name": "pandas",
                "references": [
                    {
                        "name": "pandas",
                        "source": {"path": f"{tmp_path}/requirements.txt"},
                    },
                ],
            },
        ],
    }
    output, _errors, returncode = run_fawltydeps(
        "--check", "--json", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert json.loads(output) == expect
    assert returncode == 3  # --json does not affect exit code


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
    expect_logs = (
        f"INFO:fawltydeps.extract_imports:Parsing Python files under {tmp_path}"
    )
    output, errors, returncode = run_fawltydeps(
        "--check-undeclared", "-v", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == expect_logs
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
    expect_logs = (
        f"INFO:fawltydeps.extract_imports:Parsing Python files under {tmp_path}"
    )
    output, errors, returncode = run_fawltydeps(
        "--check-unused", "-v", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == expect_logs
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
    expect_logs = (
        f"INFO:fawltydeps.extract_imports:Parsing Python files under {tmp_path}"
    )
    output, errors, returncode = run_fawltydeps(
        f"--code={tmp_path}", "-v", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == expect_logs
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
        "    code.py:1",
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas' declared in:",
        "    requirements.txt",
    ]
    expect_logs = "INFO:fawltydeps.extract_imports:Parsing Python files under ."
    output, errors, returncode = run_fawltydeps("-v", cwd=tmp_path)
    assert output.splitlines() == expect
    assert errors == expect_logs
    assert returncode == 3


def test__quiet_check__writes_only_names_of_unused_and_undeclared(
    project_with_code_and_requirements_txt,
):
    tmp_path = project_with_code_and_requirements_txt(
        imports=["requests"],
        declares=["pandas"],
    )

    expect = [
        "These imports appear to be undeclared dependencies:",
        "- 'requests'",
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas'",
        "",
        "For a more verbose report re-run with the `-v` option.",
    ]
    output, errors, returncode = run_fawltydeps("--check", cwd=tmp_path)
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode == 3
