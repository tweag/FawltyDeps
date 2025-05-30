"""Verify behavior of command-line interface.

This is more of an integration test than a unit test, in that we test the
overall behavior of the command line interface, rather than testing our
core exhaustively (which is what the other unit tests are for.
"""

import json
import logging
from dataclasses import dataclass, field
from itertools import dropwhile
from pathlib import Path
from textwrap import dedent

import pytest
from importlib_metadata import files as package_files

from fawltydeps.main import (
    UNDECLARED_DEPS_OUTPUT_PREFIX,
    UNUSED_DEPS_OUTPUT_PREFIX,
    VERBOSE_PROMPT,
    Analysis,
    version,
)
from fawltydeps.settings import DEFAULT_IGNORE_UNUSED
from fawltydeps.types import Location, UnusedDependency
from fawltydeps.utils import site_packages

from .test_extract_imports_simple import generate_notebook
from .utils import (
    assert_unordered_equivalence,
    dedent_bytes,
    run_fawltydeps_function,
    run_fawltydeps_subprocess,
)

logger = logging.getLogger(__name__)


EXIT_SUCCESS = 0
EXIT_EXCEPTION = 1
EXIT_CLI_PARSE_ERROR = 2
EXIT_UNDECLARED = 3
EXIT_UNUSED = 4
EXIT_UNRESOLVED = 5


def make_json_settings_dict(**customizations):
    """Create an expected version of Settings.dict(), with customizations."""
    defaults = {
        "actions": ["check_undeclared", "check_unused"],
        "code": ["."],
        "deps": ["."],
        "pyenvs": ["."],
        "custom_mapping": None,
        "output_format": "human_summary",
        "ignore_undeclared": [],
        "ignore_unused": sorted(DEFAULT_IGNORE_UNUSED),
        "deps_parser_choice": None,
        "install_deps": False,
        "exclude": [".*"],
        "exclude_from": [],
        "verbosity": 0,
        "custom_mapping_file": [],
        "base_dir": None,
    }
    assert all(k in defaults for k in customizations)
    return defaults | customizations


@pytest.mark.parametrize(
    ("cli_options", "expect_output", "expect_logs"),
    [
        pytest.param(
            ["--detailed", "--verbose"],
            [
                f"<stdin>:{n}: {i}"
                for i, n in [("my_requests", 4), ("foo", 5), ("my_numpy", 6)]
            ],
            ["INFO:fawltydeps.extract_imports:Parsing Python code from standard input"],
            id="detailed",
        ),
        pytest.param(
            ["--summary"],
            ["foo", "my_numpy", "my_requests", "", VERBOSE_PROMPT],
            [],
            id="summary",
        ),
    ],
)
def test_list_imports__from_dash__prints_imports_from_stdin(
    cli_options, expect_output, expect_logs
):
    code = dedent(
        """\
        from pathlib import Path
        import platform, sys

        import my_requests
        from foo import bar, baz
        import my_numpy as np
        """
    )

    output, errors, returncode = run_fawltydeps_subprocess(
        "--list-imports", "--code=-", *cli_options, to_stdin=code
    )
    assert output.splitlines() == expect_output
    assert_unordered_equivalence(errors.splitlines(), expect_logs)
    assert returncode == EXIT_SUCCESS


def test_list_imports__from_py_file__prints_imports_from_file(write_tmp_files):
    tmp_path = write_tmp_files(
        {
            "myfile.py": """\
                from pathlib import Path
                import platform, sys

                import my_requests
                from foo import bar, baz
                import my_numpy as np
                """,
        }
    )

    expect = [
        f"{tmp_path / 'myfile.py'}:{n}: {i}"
        for i, n in [("my_requests", 4), ("foo", 5), ("my_numpy", 6)]
    ]
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--detailed", f"--code={tmp_path / 'myfile.py'}"
    )
    assert output.splitlines() == expect
    assert returncode == EXIT_SUCCESS


def test_list_imports_json__from_py_file__prints_imports_from_file(write_tmp_files):
    tmp_path = write_tmp_files(
        {
            "myfile.py": """\
                from pathlib import Path
                import platform, sys

                import my_requests
                from foo import bar, baz
                import my_numpy as np
                """,
        }
    )

    expect = {
        "settings": make_json_settings_dict(
            actions=["list_imports"],
            code=[f"{tmp_path / 'myfile.py'}"],
            output_format="json",
        ),
        "sources": [
            {
                "source_type": "CodeSource",
                "path": f"{tmp_path / 'myfile.py'}",
                "base_dir": None,
            },
        ],
        "imports": [
            {
                "name": "my_requests",
                "source": {"path": f"{tmp_path / 'myfile.py'}", "lineno": 4},
            },
            {
                "name": "foo",
                "source": {"path": f"{tmp_path / 'myfile.py'}", "lineno": 5},
            },
            {
                "name": "my_numpy",
                "source": {"path": f"{tmp_path / 'myfile.py'}", "lineno": 6},
            },
        ],
        "declared_deps": None,
        "resolved_deps": None,
        "undeclared_deps": None,
        "unused_deps": None,
        "version": version(),
    }
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--json", f"--code={tmp_path / 'myfile.py'}"
    )
    assert json.loads(output) == expect
    assert returncode == EXIT_SUCCESS


def test_list_imports__from_ipynb_file__prints_imports_from_file(write_tmp_files):
    tmp_path = write_tmp_files(
        {
            "myfile.ipynb": generate_notebook([["import pytorch"]]),
        }
    )

    expect = [f"{tmp_path / 'myfile.ipynb'}[1]:1: pytorch"]
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--detailed", f"--code={tmp_path / 'myfile.ipynb'}"
    )
    assert output.splitlines() == expect
    assert returncode == EXIT_SUCCESS


def test_list_imports__from_dir__prints_imports_from_py_and_ipynb_files_only(
    write_tmp_files,
):
    notebook_content = generate_notebook([["import pytorch"]])
    tmp_path = write_tmp_files(
        {
            "file1.py": """\
                from my_pathlib import Path
                import my_pandas, scipy
                """,
            "file2.NOT_PYTHON": """\
                import my_requests
                from foo import bar, baz
                import my_numpy as np
                """,
            "file3.ipynb": notebook_content,
        }
    )

    expect = [
        f"{tmp_path / 'file1.py'}:{n}: {i}"
        for i, n in [("my_pathlib", 1), ("my_pandas", 2), ("scipy", 2)]
    ] + [f"{tmp_path / 'file3.ipynb'}[1]:1: pytorch"]
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--detailed", f"--code={tmp_path}"
    )
    assert output.splitlines() == expect
    assert returncode == EXIT_SUCCESS


def test_list_imports__from_dir_with_some_excluded__prints_imports_from_unexcluded_only(
    write_tmp_files,
):
    notebook_content = generate_notebook([["import pytorch"]])
    tmp_path = write_tmp_files(
        {
            "file1.py": """\
                from my_pathlib import Path
                import my_pandas, scipy
                """,
            "file2.NOT_PYTHON": """\
                import my_requests
                from foo import bar, baz
                import my_numpy as np
                """,
            "file3.ipynb": notebook_content,
        }
    )

    expect = [f"{tmp_path / 'file3.ipynb'}[1]:1: pytorch"]
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--detailed", f"--code={tmp_path}", "--exclude=*.py"
    )
    assert output.splitlines() == expect
    assert returncode == EXIT_SUCCESS


def test_list_imports__from_unsupported_file__fails_with_exit_code_2(tmp_path):
    filepath = tmp_path / "test.NOT_SUPPORTED"
    filepath.write_text("import my_pandas")
    _output, errors, returncode = run_fawltydeps_subprocess(
        "--list-imports", f"--code={filepath}"
    )
    assert (
        f"Supported formats are .py and .ipynb; Cannot parse code: {filepath}" in errors
    )
    assert returncode == EXIT_CLI_PARSE_ERROR


def test_list_imports__from_missing_file__fails_with_exit_code_2(tmp_path):
    missing_path = tmp_path / "MISSING.py"
    _output, errors, returncode = run_fawltydeps_subprocess(
        "--list-imports", f"--code={missing_path}"
    )
    assert f"Code path to parse is neither dir nor file: {missing_path}" in errors
    assert returncode == EXIT_CLI_PARSE_ERROR


def test_list_imports__missing_exclude_pattern__fails_with_exit_code_2():
    _output, errors, returncode = run_fawltydeps_subprocess(
        "--list-imports", "--exclude="
    )
    assert "Error while parsing exclude pattern: No rule found: ''" in errors
    assert returncode == EXIT_CLI_PARSE_ERROR


def test_list_imports__comment_in_exclude_pattern__fails_with_exit_code_2():
    _output, errors, returncode = run_fawltydeps_subprocess(
        "--list-imports", "--exclude", "# comment"
    )
    assert "Error while parsing exclude pattern: No rule found: '# comment'" in errors
    assert returncode == EXIT_CLI_PARSE_ERROR


def test_list_imports__from_empty_dir__logs_but_extracts_nothing(tmp_path):
    # Enable log level INFO with --verbose
    expect_logs = [
        f"INFO:fawltydeps.extract_imports:Finding Python files under {tmp_path}",
    ]
    output, errors, returncode = run_fawltydeps_subprocess(
        "--list-imports", f"--code={tmp_path}", "--detailed", "--verbose"
    )
    assert output == ""
    assert_unordered_equivalence(errors.splitlines(), expect_logs)
    assert returncode == EXIT_SUCCESS


def test_list_imports__pick_multiple_files_dir__prints_all_imports(
    project_with_multiple_python_files,
):
    path_code1 = project_with_multiple_python_files / "subdir"
    path_code2 = project_with_multiple_python_files / "python_file.py"
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--code", f"{path_code1}", f"{path_code2}"
    )
    expect = ["django", "pandas", "click"]
    assert_unordered_equivalence(output.splitlines()[:-2], expect)
    assert returncode == EXIT_SUCCESS


def test_list_imports__pick_multiple_files_dir_and_code__prints_all_imports(
    project_with_multiple_python_files,
):
    code = dedent(
        """\
        from pathlib import Path
        import platform, sys

        import my_requests
        from foo import bar, baz
        import my_numpy as np
        """
    )
    path_code2 = project_with_multiple_python_files / "python_file.py"
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--code", "-", f"{path_code2}", to_stdin=code
    )
    expect = ["django", "my_requests", "foo", "my_numpy"]
    assert_unordered_equivalence(output.splitlines()[:-2], expect)
    assert returncode == EXIT_SUCCESS


def test_list_imports__stdin_with_legacy_encoding__prints_all_imports():
    code = dedent_bytes(
        b"""\
        # -*- coding: big5 -*-

        # Some Traditional Chinese characters:
        chars = "\xa4@\xa8\xc7\xa4\xa4\xa4\xe5\xa6r\xb2\xc5"

        import my_numpy
        """
    )
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--code", "-", to_stdin=code
    )
    expect = ["my_numpy"]
    assert_unordered_equivalence(output.splitlines()[:-2], expect)
    assert returncode == EXIT_SUCCESS


def test_list_deps_detailed__dir__prints_deps_from_requirements_txt(fake_project):
    tmp_path = fake_project(
        imports=["my_requests", "my_pandas"],
        declared_deps=["my_requests", "my_pandas"],
    )

    expect = [
        f"{tmp_path / 'requirements.txt'}: my_pandas",
        f"{tmp_path / 'requirements.txt'}: my_requests",
    ]
    output, returncode = run_fawltydeps_function(
        "--list-deps", "--detailed", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert returncode == EXIT_SUCCESS


def test_list_deps_json__dir__prints_deps_from_requirements_txt(fake_project):
    tmp_path = fake_project(
        imports=["my_requests", "my_pandas"],
        declared_deps=["my_requests", "my_pandas"],
    )

    expect = {
        "settings": make_json_settings_dict(
            actions=["list_deps"], deps=[f"{tmp_path}"], output_format="json"
        ),
        "sources": [
            {
                "source_type": "DepsSource",
                "path": f"{tmp_path / 'requirements.txt'}",
                "parser_choice": "requirements.txt",
            },
        ],
        "imports": None,
        "declared_deps": [
            {
                "name": "my_requests",
                "source": {"path": f"{tmp_path / 'requirements.txt'}"},
            },
            {
                "name": "my_pandas",
                "source": {"path": f"{tmp_path / 'requirements.txt'}"},
            },
        ],
        "resolved_deps": None,
        "undeclared_deps": None,
        "unused_deps": None,
        "version": version(),
    }
    output, returncode = run_fawltydeps_function(
        "--list-deps", "--json", f"--deps={tmp_path}"
    )
    assert json.loads(output) == expect
    assert returncode == EXIT_SUCCESS


def test_list_deps_summary__dir__prints_deps_from_requirements_txt(fake_project):
    tmp_path = fake_project(
        imports=["my_requests", "my_pandas"],
        declared_deps=["my_requests", "my_pandas"],
    )

    expect = ["my_pandas", "my_requests"]
    output, returncode = run_fawltydeps_function("--list-deps", f"--deps={tmp_path}")
    assert output.splitlines()[:-2] == expect
    assert returncode == EXIT_SUCCESS


def test_list_deps__unsupported_file__fails_with_exit_code_2(tmp_path):
    filepath = tmp_path / "test.NOT_SUPPORTED"
    filepath.write_text("my_pandas\n")

    _output, errors, returncode = run_fawltydeps_subprocess(
        "--list-deps", f"--deps={filepath}"
    )
    assert returncode == EXIT_CLI_PARSE_ERROR
    assert f"Parsing given dependencies path isn't supported: {filepath}" in errors


def test_list_deps__missing_path__fails_with_exit_code_2(tmp_path):
    missing_path = tmp_path / "MISSING_PATH"

    _output, errors, returncode = run_fawltydeps_subprocess(
        "--list-deps", f"--deps={missing_path}"
    )
    assert returncode == EXIT_CLI_PARSE_ERROR
    assert (
        f"Dependencies declaration path is neither dir nor file: {missing_path}"
        in errors
    )


def test_list_deps__empty_dir__verbosely_logs_but_extracts_nothing(tmp_path):
    # Enable log level INFO with --verbose
    output, errors, returncode = run_fawltydeps_subprocess(
        "--list-deps", f"--deps={tmp_path}", "--detailed", "--verbose"
    )
    assert output == ""
    assert errors == ""  # TODO: Should there be a INFO-level log message here?
    assert returncode == EXIT_SUCCESS


def test_list_deps__pick_multiple_listed_files__prints_all_dependencies(
    project_with_setup_and_requirements,
):
    path_deps1 = project_with_setup_and_requirements / "subdir/requirements.txt"
    path_deps2 = project_with_setup_and_requirements / "setup.py"
    output, returncode = run_fawltydeps_function(
        "--list-deps", "--deps", f"{path_deps1}", f"{path_deps2}"
    )
    expect = ["annoy", "jieba", "click", "pandas", "tensorflow"]
    assert_unordered_equivalence(output.splitlines()[:-2], expect)
    assert returncode == EXIT_SUCCESS


def test_list_sources__in_empty_project__lists_nothing(tmp_path):
    output, returncode = run_fawltydeps_function("--list-sources", f"{tmp_path}")
    expect = []
    assert_unordered_equivalence(output.splitlines()[:-2], expect)
    assert returncode == EXIT_SUCCESS


def test_list_sources__in_varied_project__lists_all_files(fake_project):
    tmp_path = fake_project(
        files_with_imports={
            "code.py": ["foo"],
            str(Path("subdir", "other.py")): ["foo"],
            str(Path("subdir", "notebook.ipynb")): ["foo"],
        },
        files_with_declared_deps={
            "requirements.txt": ["foo"],
            "pyproject.toml": ["foo"],
            "setup.py": ["foo"],
            "setup.cfg": ["foo"],
            "environment.yml": ["foo"],
        },
        fake_venvs={"my_venv": {}},
    )
    output, returncode = run_fawltydeps_function("--list-sources", f"{tmp_path}")

    _site_packages = site_packages(Path("my_venv"))

    expect = [
        str(tmp_path / filename)
        for filename in [
            "code.py",
            str(Path("subdir", "other.py")),
            str(Path("subdir", "notebook.ipynb")),
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "environment.yml",
            str(_site_packages),
        ]
    ]
    assert_unordered_equivalence(output.splitlines()[:-2], expect)
    assert returncode == EXIT_SUCCESS


def test_list_sources_detailed__in_varied_project__lists_all_files(fake_project):
    tmp_path = fake_project(
        files_with_imports={
            "code.py": ["foo"],
            str(Path("subdir", "notebook.ipynb")): ["foo"],
            str(Path("subdir", "other.py")): ["foo"],
        },
        files_with_declared_deps={
            "pyproject.toml": ["foo"],
            "requirements.txt": ["foo"],
            "setup.cfg": ["foo"],
            "setup.py": ["foo"],
            "pixi.toml": ["foo"],
        },
        fake_venvs={"my_venv": {}},
    )
    output, returncode = run_fawltydeps_function(
        "--list-sources", str(tmp_path), "--detailed"
    )
    expect_code_lines = [
        f"  {tmp_path / filename} (using {tmp_path} as base for 1st-party imports)"
        for filename in [
            "code.py",
            "setup.py",  # This is both a CodeSource and an DepsSource!
            str(Path("subdir", "notebook.ipynb")),
            str(Path("subdir", "other.py")),
        ]
    ]
    expect_deps_lines = [
        f"  {tmp_path / filename} (parsed as a {filename} file)"
        for filename in [
            "pixi.toml",
            "pyproject.toml",
            "requirements.txt",
            "setup.cfg",
            "setup.py",
        ]
    ]
    _site_packages = site_packages(tmp_path / "my_venv")
    expect_pyenv_lines = [
        "  " + str(_site_packages) + " (as a source of Python packages)",
    ]
    expect = [
        "Sources of Python code:",
        *expect_code_lines,
        "",
        "Sources of declared dependencies:",
        *expect_deps_lines,
        "",
        "Python environments:",
        *expect_pyenv_lines,
    ]
    assert output.splitlines() == expect
    assert returncode == EXIT_SUCCESS


def test_list_sources_detailed__from_both_python_file_and_stdin(fake_project):
    tmp_path = fake_project(files_with_imports={"code.py": ["foo"]})
    output, returncode = run_fawltydeps_function(
        "--list-sources", f"{tmp_path}", "--code", f"{tmp_path}", "-", "--detailed"
    )
    expect = [
        [
            "Sources of Python code:",
            f"  {tmp_path / 'code.py'} (using {tmp_path} as base for 1st-party imports)",
            "  <stdin>",
        ],
        [
            "Sources of Python code:",
            "  <stdin>",
            f"  {tmp_path / 'code.py'} (using {tmp_path} as base for 1st-party imports)",
        ],
    ]
    assert output.splitlines() in expect
    assert returncode == EXIT_SUCCESS


def test_list_sources__with_exclude_from(fake_project):
    tmp_path = fake_project(
        files_with_imports={
            "code.py": ["foo"],
            str(Path("subdir", "notebook.ipynb")): ["foo"],
            str(Path("subdir", "other.py")): ["foo"],
        },
        files_with_declared_deps={
            "pyproject.toml": ["foo"],
            "requirements.txt": ["foo"],
            "setup.cfg": ["foo"],
            "setup.py": ["foo"],
            "pixi.toml": ["foo"],
        },
        fake_venvs={"venvs/my_venv": {}},
        extra_file_contents={
            "my_ignore": dedent(
                """
                subdir/*.py
                /setup.*
                *envs
                pixi.toml
                """
            )
        },
    )
    output, returncode = run_fawltydeps_function(
        "--list-sources", f"{tmp_path}", "--exclude-from", f"{tmp_path / 'my_ignore'}"
    )
    expect = [
        str(tmp_path / filename)
        for filename in [
            "code.py",
            str(Path("subdir", "notebook.ipynb")),
            "requirements.txt",
            "pyproject.toml",
        ]
    ]
    assert_unordered_equivalence(output.splitlines()[:-2], expect)
    assert returncode == 0


@dataclass
class ProjectTestVector:
    """Test vectors for FawltyDeps Settings configuration."""

    id: str
    options: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    declares: list[str] = field(default_factory=list)

    expect_output: list[str] = field(default_factory=list)
    expect_logs: list[str] = field(default_factory=list)
    expect_returncode: int = EXIT_SUCCESS


full_success_message = (
    Analysis.success_message(check_undeclared=True, check_unused=True) or ""
)

project_tests_samples = [
    ProjectTestVector(
        id="simple_project_imports_match_dependencies__prints_verbose_option",
        options=["--check", "--code={path}", "--deps={path}"],
        imports=["my_requests", "my_pandas"],
        declares=["my_requests", "my_pandas"],
        expect_output=[full_success_message],
    ),
    ProjectTestVector(
        id="simple_project_with_missing_deps__reports_undeclared",
        options=["--check", "--detailed", "--code={path}", "--deps={path}"],
        imports=["my_requests", "my_pandas"],
        declares=["my_pandas"],
        expect_output=[
            f"{UNDECLARED_DEPS_OUTPUT_PREFIX}:",
            "- 'my_requests'",
            "    imported at:",
            f"      {Path('{path}', 'code.py')}:1",
        ],
        expect_returncode=EXIT_UNDECLARED,
    ),
    ProjectTestVector(
        id="simple_project_with_extra_deps__reports_unused",
        options=["--check", "--detailed", "--code={path}", "--deps={path}"],
        imports=["my_requests"],
        declares=["my_requests", "my_pandas"],
        expect_output=[
            f"{UNUSED_DEPS_OUTPUT_PREFIX}:",
            "- 'my_pandas'",
            "    declared in:",
            f"      {Path('{path}', 'requirements.txt')}",
        ],
        expect_returncode=EXIT_UNUSED,
    ),
    ProjectTestVector(
        id="simple_project_with_extra_deps__reports_unused_and_undeclared",
        options=["--check", "--detailed", "--code={path}", "--deps={path}"],
        imports=["my_requests"],
        declares=["my_pandas"],
        expect_output=[
            f"{UNDECLARED_DEPS_OUTPUT_PREFIX}:",
            "- 'my_requests'",
            "    imported at:",
            f"      {Path('{path}', 'code.py')}:1",
            "",
            f"{UNUSED_DEPS_OUTPUT_PREFIX}:",
            "- 'my_pandas'",
            "    declared in:",
            f"      {Path('{path}', 'requirements.txt')}",
        ],
        expect_returncode=EXIT_UNDECLARED,  # undeclared is more important than unused
    ),
    ProjectTestVector(
        id="simple_project__summary_report_with_verbose_logging",
        options=["--check", "--summary", "--verbose", "--code={path}", "--deps={path}"],
        imports=["my_requests"],
        declares=["my_pandas"],
        expect_output=[
            f"{UNDECLARED_DEPS_OUTPUT_PREFIX}:",
            "- 'my_requests'",
            "",
            f"{UNUSED_DEPS_OUTPUT_PREFIX}:",
            "- 'my_pandas'",
            "",
            VERBOSE_PROMPT,
        ],
        expect_logs=[
            "INFO:fawltydeps.extract_imports:Finding Python files under {path}",
            "INFO:fawltydeps.extract_imports:Parsing Python file "
            f"{Path('{path}', 'code.py')}",
            "INFO:fawltydeps.packages:'my_pandas' was not resolved."
            " Assuming it can be imported as 'my_pandas'.",
        ],
        expect_returncode=EXIT_UNDECLARED,  # undeclared is more important than unused
    ),
    ProjectTestVector(
        id="simple_project__summary_report_with_quiet_logging",
        options=["--check", "--detailed", "--code={path}", "--deps={path}"],
        imports=["my_requests"],
        declares=["my_pandas"],
        expect_output=[
            f"{UNDECLARED_DEPS_OUTPUT_PREFIX}:",
            "- 'my_requests'",
            "    imported at:",
            f"      {Path('{path}', 'code.py')}:1",
            "",
            f"{UNUSED_DEPS_OUTPUT_PREFIX}:",
            "- 'my_pandas'",
            "    declared in:",
            f"      {Path('{path}', 'requirements.txt')}",
        ],
        expect_returncode=EXIT_UNDECLARED,  # undeclared is more important than unused
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in project_tests_samples]
)
def test_check_undeclared_and_unused(vector, fake_project):
    tmp_path = fake_project(
        imports=vector.imports,
        declared_deps=vector.declares,
    )
    output, errors, returncode = run_fawltydeps_subprocess(
        *[option.format(path=tmp_path) for option in vector.options]
    )
    # Order of output is determined, as we use alphabetical ordering.
    assert output.splitlines() == [
        line.format(path=tmp_path) for line in vector.expect_output
    ]
    # Order of log messages is not important.
    assert_unordered_equivalence(
        errors.splitlines(),
        [line.format(path=tmp_path) for line in vector.expect_logs],
    )
    assert returncode == vector.expect_returncode


def test_check_json__simple_project__can_report_both_undeclared_and_unused(
    fake_project,
):
    tmp_path = fake_project(
        imports=["my_requests"],
        declared_deps=["my_pandas"],
        fake_venvs={"my_venv": {}},
    )

    expect = {
        "settings": make_json_settings_dict(
            code=[f"{tmp_path}"],
            deps=[f"{tmp_path}"],
            pyenvs=[f"{tmp_path}"],
            output_format="json",
        ),
        "sources": [
            {
                "source_type": "CodeSource",
                "path": f"{tmp_path / 'code.py'}",
                "base_dir": f"{tmp_path}",
            },
            {
                "source_type": "DepsSource",
                "path": f"{tmp_path / 'requirements.txt'}",
                "parser_choice": "requirements.txt",
            },
            {
                "source_type": "PyEnvSource",
                "path": f"{site_packages(tmp_path / 'my_venv')}",
            },
        ],
        "imports": [
            {
                "name": "my_requests",
                "source": {"path": f"{tmp_path / 'code.py'}", "lineno": 1},
            },
        ],
        "declared_deps": [
            {
                "name": "my_pandas",
                "source": {"path": f"{tmp_path / 'requirements.txt'}"},
            },
        ],
        "resolved_deps": {
            "my_pandas": {
                "package_name": "my_pandas",
                "import_names": ["my_pandas"],
                "resolved_with": "IdentityMapping",
                "debug_info": None,
            }
        },
        "undeclared_deps": [
            {
                "name": "my_requests",
                "references": [{"path": f"{tmp_path / 'code.py'}", "lineno": 1}],
                "candidates": [],
            },
        ],
        "unused_deps": [
            {
                "name": "my_pandas",
                "references": [{"path": f"{tmp_path / 'requirements.txt'}"}],
            },
        ],
        "version": version(),
    }
    output, returncode = run_fawltydeps_function(
        "--check",
        "--json",
        f"--code={tmp_path}",
        f"--deps={tmp_path}",
        f"--pyenv={tmp_path}",
    )
    assert json.loads(output) == expect
    assert returncode == EXIT_UNDECLARED  # --json does not affect exit code


def test_check_undeclared__simple_project__reports_only_undeclared(fake_project):
    tmp_path = fake_project(
        imports=["my_requests"],
        declared_deps=["my_pandas"],
    )

    expect = [
        f"{UNDECLARED_DEPS_OUTPUT_PREFIX}:",
        "- 'my_requests'",
        "    imported at:",
        f"      {tmp_path / 'code.py'}:1",
    ]
    output, returncode = run_fawltydeps_function(
        "--check-undeclared",
        "--detailed",
        f"--code={tmp_path}",
        "--deps",
        f"{tmp_path}",
    )
    assert output.splitlines() == expect
    assert returncode == EXIT_UNDECLARED


def test_check_unused__simple_project__reports_only_unused(fake_project):
    tmp_path = fake_project(
        imports=["my_requests"],
        declared_deps=["my_pandas"],
    )

    expect = [
        f"{UNUSED_DEPS_OUTPUT_PREFIX}:",
        "- 'my_pandas'",
        "    declared in:",
        f"      {tmp_path / 'requirements.txt'}",
    ]
    output, returncode = run_fawltydeps_function(
        "--check-unused",
        "--detailed",
        f"--code={tmp_path}",
        "--deps",
        f"{tmp_path}",
    )
    assert output.splitlines() == expect
    assert returncode == EXIT_UNUSED


def test__no_action__defaults_to_check_action(fake_project):
    tmp_path = fake_project(
        imports=["my_requests"],
        declared_deps=["my_pandas"],
    )

    expect = [
        f"{UNDECLARED_DEPS_OUTPUT_PREFIX}:",
        "- 'my_requests'",
        "    imported at:",
        f"      {tmp_path / 'code.py'}:1",
        "",
        f"{UNUSED_DEPS_OUTPUT_PREFIX}:",
        "- 'my_pandas'",
        "    declared in:",
        f"      {tmp_path / 'requirements.txt'}",
    ]
    output, returncode = run_fawltydeps_function(
        f"--code={tmp_path}", "--detailed", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert returncode == EXIT_UNDECLARED


def test__no_options__defaults_to_check_action_in_current_dir(fake_project):
    tmp_path = fake_project(
        imports=["my_requests"],
        declared_deps=["my_pandas"],
    )

    expect = [
        f"{UNDECLARED_DEPS_OUTPUT_PREFIX}:",
        "- 'my_requests'",
        "    imported at:",
        "      code.py:1",
        "",
        f"{UNUSED_DEPS_OUTPUT_PREFIX}:",
        "- 'my_pandas'",
        "    declared in:",
        "      requirements.txt",
    ]
    expect_logs = []
    output, errors, returncode = run_fawltydeps_subprocess("--detailed", cwd=tmp_path)
    assert output.splitlines() == expect
    assert_unordered_equivalence(errors.splitlines(), expect_logs)
    assert returncode == EXIT_UNDECLARED


def test_check__summary__writes_only_names_of_unused_and_undeclared(fake_project):
    tmp_path = fake_project(
        imports=["my_requests"],
        declared_deps=["my_pandas"],
    )

    expect = [
        f"{UNDECLARED_DEPS_OUTPUT_PREFIX}:",
        "- 'my_requests'",
        "",
        f"{UNUSED_DEPS_OUTPUT_PREFIX}:",
        "- 'my_pandas'",
        "",
        VERBOSE_PROMPT,
    ]
    output, returncode = run_fawltydeps_function("--check", basepath=tmp_path)
    assert output.splitlines() == expect
    assert returncode == EXIT_UNDECLARED


def test_check_detailed__simple_project_in_fake_venv__resolves_imports_vs_deps(
    fake_project,
):
    tmp_path = fake_project(
        imports=["my_requests"],
        declared_deps=["my_pandas"],
        # A venv where the "my_pandas" package provides a "my_requests" import name
        # should satisfy our comparison
        fake_venvs={".venv": {"my_pandas": {"my_requests"}}},
    )

    output, returncode = run_fawltydeps_function(
        "--detailed",
        f"--code={tmp_path}",
        f"--deps={tmp_path}",
        f"--pyenv={tmp_path}/.venv",
    )
    assert output.splitlines() == [
        Analysis.success_message(check_undeclared=True, check_unused=True),
    ]
    assert returncode == EXIT_SUCCESS


def test_check_detailed__simple_project_w_2_fake_venv__resolves_imports_vs_deps(
    fake_project,
):
    tmp_path = fake_project(
        imports=["some_import", "other_import", "yet_another"],
        declared_deps=["something", "other"],
        fake_venvs={
            "venv1": {"something": {"some_import"}},
            "venv2": {"something": {"other_import"}, "other": {"yet_another"}},
        },
    )

    output, returncode = run_fawltydeps_function(
        "--detailed", f"{tmp_path}", "--pyenv", f"{tmp_path}/venv1", f"{tmp_path}/venv2"
    )
    assert output.splitlines() == [
        Analysis.success_message(check_undeclared=True, check_unused=True),
    ]
    assert returncode == EXIT_SUCCESS


def test_check_detailed__shows_package_suggerstions_for_undeclared_deps(
    fake_project,
):
    tmp_path = fake_project(
        imports=["some_import", "other_import", "yet_another"],
        fake_venvs={
            ".venv": {
                "some_package": {"some_import", "other_import"},
                "other_package": {"other_import"},
            },
        },
    )

    output, returncode = run_fawltydeps_function("--detailed", f"{tmp_path}")
    expect = [
        f"{UNDECLARED_DEPS_OUTPUT_PREFIX}:",
        "- 'other_import'",
        "    imported at:",
        f"      {tmp_path / 'code.py'}:2",
        "    may be provided by these packages:",
        "      'other_package'",
        "      'some_package'",
        "- 'some_import'",
        "    imported at:",
        f"      {tmp_path / 'code.py'}:1",
        "    may be provided by these packages:",
        "      'some_package'",
        "- 'yet_another'",
        "    imported at:",
        f"      {tmp_path / 'code.py'}:3",
    ]
    assert output.splitlines() == expect
    assert returncode == EXIT_UNDECLARED


def test_check_json__no_pyenvs_found__falls_back_to_current_env(fake_project):
    # When using the _current_ env (aka. sys.path), we can assume that FD's
    # own dependencies (such as "pip-requirements-parser", providing the
    # "pip_requirements_parser" and "packaging_legacy_version" import names)
    # will be present/resolved, but "other_module" must rely on falling back to
    # the identity mapping.
    tmp_path = fake_project(
        imports=["packaging_legacy_version", "other_module"],
        declared_deps=["pip-requirements-parser", "other_module"],
    )

    # Find the expected site-packages directory containing
    # pip-requirements-parser in the current environment
    site_packages = package_files("pip-requirements-parser")[0].locate()
    while site_packages.name != "site-packages":
        site_packages = site_packages.parent

    expect = {
        "settings": make_json_settings_dict(
            code=[f"{tmp_path}"],
            deps=[f"{tmp_path}"],
            pyenvs=[f"{tmp_path}"],
            output_format="json",
        ),
        "sources": [
            {
                "source_type": "CodeSource",
                "path": f"{tmp_path / 'code.py'}",
                "base_dir": f"{tmp_path}",
            },
            {
                "source_type": "DepsSource",
                "path": f"{tmp_path / 'requirements.txt'}",
                "parser_choice": "requirements.txt",
            },
            # No PyEnvSources found
        ],
        "imports": [
            {
                "name": "packaging_legacy_version",
                "source": {"path": f"{tmp_path / 'code.py'}", "lineno": 1},
            },
            {
                "name": "other_module",
                "source": {"path": f"{tmp_path / 'code.py'}", "lineno": 2},
            },
        ],
        "declared_deps": [
            {
                "name": "pip-requirements-parser",
                "source": {"path": f"{tmp_path / 'requirements.txt'}"},
            },
            {
                "name": "other_module",
                "source": {"path": f"{tmp_path / 'requirements.txt'}"},
            },
        ],
        "resolved_deps": {
            "pip-requirements-parser": {
                "package_name": "pip-requirements-parser",
                "import_names": ["packaging_legacy_version", "pip_requirements_parser"],
                "resolved_with": "SysPathPackageResolver",
                "debug_info": {
                    f"{site_packages}": [
                        "packaging_legacy_version",
                        "pip_requirements_parser",
                    ],
                },
            },
            "other_module": {
                "package_name": "other_module",
                "import_names": ["other_module"],
                "resolved_with": "IdentityMapping",
                "debug_info": None,
            },
        },
        "undeclared_deps": [],
        "unused_deps": [],
        "version": version(),
    }
    output, returncode = run_fawltydeps_function("--check", "--json", f"{tmp_path}")
    assert json.loads(output) == expect
    assert returncode == EXIT_SUCCESS  # --json does not affect exit code


@pytest.mark.parametrize(
    ("args", "imports", "dependencies", "expected"),
    [
        pytest.param(
            ["--check-unused"],
            ["my_requests"],
            ["black", "mypy"],
            [Analysis.success_message(check_undeclared=False, check_unused=True)],
            id="check_unused_action_on_default_ignored_unused_dep__outputs_nothing",
        ),
        pytest.param(
            ["--check-unused", "--ignore-unused", "black", "my_pandas"],
            ["my_requests"],
            ["black", "my_pandas"],
            [Analysis.success_message(check_undeclared=False, check_unused=True)],
            id="check_unused_action_on_overriden_ignored_unused_dep__outputs_nothing",
        ),
        pytest.param(
            ["--list-deps", "--ignore-unused", "my_numpy"],
            [],
            ["my_numpy"],
            ["my_numpy", "", VERBOSE_PROMPT],
            id="list_deps_action_on_ignored_dep__reports_dep",
        ),
        pytest.param(
            ["--check-undeclared", "--ignore-unused", "my_pandas"],
            ["my_pandas"],
            ["my_pandas"],
            [Analysis.success_message(check_undeclared=True, check_unused=False)],
            id="check_undeclared_action_on_ignored_declared_dep__does_not_report_dep_as_undeclared",
        ),
        pytest.param(
            ["--check-undeclared", "--ignore-undeclared", "black", "mypy"],
            ["black", "mypy"],
            ["my_numpy"],
            [Analysis.success_message(check_undeclared=True, check_unused=False)],
            id="check_undeclared_action_on_ignored_undeclared_import__outputs_nothing",
        ),
        pytest.param(
            ["--list-imports", "--ignore-undeclared", "isort"],
            ["isort"],
            [],
            ["isort", "", VERBOSE_PROMPT],
            id="list_imports_action_on_ignored_imports__reports_imports",
        ),
        pytest.param(
            ["--check-unused", "--ignore-undeclared", "isort"],
            ["isort"],
            ["isort"],
            [Analysis.success_message(check_undeclared=False, check_unused=True)],
            id="check_unused_action_on_ignored_but_used_import__does_not_report_dep_as_unused",
        ),
        pytest.param(
            [
                "--check",
                "--ignore-undeclared",
                "isort",
                "my_numpy",
                "--ignore-unused",
                "my_pandas",
                "tomli",
            ],
            ["isort", "my_numpy"],
            ["my_pandas", "tomli"],
            [Analysis.success_message(check_undeclared=True, check_unused=True)],
            id="check_action_on_ignored__does_not_report_ignored",
        ),
    ],
)
def test_cmdline_on_ignore_options(args, imports, dependencies, expected, fake_project):
    tmp_path = fake_project(
        imports=imports,
        declared_deps=dependencies,
    )
    output, returncode = run_fawltydeps_function(*args, basepath=tmp_path)
    assert output.splitlines() == expected
    assert returncode == EXIT_SUCCESS


@pytest.mark.parametrize(
    ("config", "args", "expect"),
    [
        pytest.param(
            {},
            [],
            [
                f"{UNDECLARED_DEPS_OUTPUT_PREFIX}:",
                "- 'my_requests'",
                "",
                f"{UNUSED_DEPS_OUTPUT_PREFIX}:",
                "- 'my_pandas'",
                "",
                VERBOSE_PROMPT,
            ],
            id="no_config_no_args__show_summary_of_undeclared_and_unused",
        ),
        pytest.param(
            {"actions": ["list_imports"]},
            [],
            [
                "my_requests",
                "",
                VERBOSE_PROMPT,
            ],
            id="setting_actions_in_config__changes_default_action",
        ),
        pytest.param(
            {"actions": ["list_imports"]},
            ["--detailed"],
            ["code.py:1: my_requests"],
            id="combine_actions_in_config_with_detailed_on_command_line",
        ),
        pytest.param(
            {"actions": ["list_imports"], "output_format": "human_detailed"},
            ["--list-deps"],
            ["requirements.txt: my_pandas"],
            id="override_some_config_directives_on_command_line",
        ),
        pytest.param(
            {"actions": ["list_imports"], "output_format": "human_detailed"},
            ["--summary"],
            [
                "my_requests",
                "",
                VERBOSE_PROMPT,
            ],
            id="override_output_format_from_config_with_command_line_option",
        ),
        pytest.param(
            {"actions": ["list_imports"], "output_format": "human_detailed"},
            ["--exclude", "code.py"],
            [],
            id="combine_actions_in_config_with_exclude_on_command_line",
        ),
        pytest.param(
            {"actions": ["list_imports"], "exclude": ["code.py"]},
            ["--exclude", ".*", "--detailed"],
            ["code.py:1: my_requests"],
            id="override_exclude_in_config_with_exclude_on_command_line",
        ),
        pytest.param(
            {"actions": ["list_imports"], "output_format": "json"},
            ["--detailed", "--deps=foobar", "--generate-toml-config"],
            dedent(
                f"""\
                # Copy this TOML section into your pyproject.toml to configure FawltyDeps
                # (default values are commented)
                [tool.fawltydeps]
                actions = ['list_imports']
                output_format = 'human_detailed'
                # code = ['.']
                deps = ['foobar']
                # pyenvs = ['.']
                # ignore_undeclared = []
                # ignore_unused = {sorted(DEFAULT_IGNORE_UNUSED)}
                # deps_parser_choice = ...
                # install_deps = false
                # exclude = ['.*']
                # exclude_from = []
                # verbosity = 0
                # custom_mapping_file = []
                # base_dir = ...
                # [tool.fawltydeps.custom_mapping]
                """
            ).splitlines(),
            id="generate_toml_config_with_combo_of_config_and_cmdline_options",
        ),
        pytest.param(
            {"actions": ["check_undeclared"]},
            ["--pyenv=None", "--generate-toml-config"],
            dedent(
                f"""\
                # Copy this TOML section into your pyproject.toml to configure FawltyDeps
                # (default values are commented)
                [tool.fawltydeps]
                actions = ['check_undeclared']
                # output_format = 'human_summary'
                # code = ['.']
                # deps = ['.']
                pyenvs = ['None']
                # ignore_undeclared = []
                # ignore_unused = {sorted(DEFAULT_IGNORE_UNUSED)}
                # deps_parser_choice = ...
                # install_deps = false
                # exclude = ['.*']
                # exclude_from = []
                # verbosity = 0
                # custom_mapping_file = []
                # base_dir = ...
                # [tool.fawltydeps.custom_mapping]
                """
            ).splitlines(),
            id="generate_toml_config_with_a_setting_set_to_str_None",
        ),
        pytest.param(
            {"pyenvs": ["foo", "bar"]},
            ["--pyenv", "baz", "xyzzy", "--generate-toml-config"],
            dedent(
                f"""\
                # Copy this TOML section into your pyproject.toml to configure FawltyDeps
                # (default values are commented)
                [tool.fawltydeps]
                # actions = ['check_undeclared', 'check_unused']
                # output_format = 'human_summary'
                # code = ['.']
                # deps = ['.']
                pyenvs = ['baz', 'xyzzy']
                # ignore_undeclared = []
                # ignore_unused = {sorted(DEFAULT_IGNORE_UNUSED)}
                # deps_parser_choice = ...
                # install_deps = false
                # exclude = ['.*']
                # exclude_from = []
                # verbosity = 0
                # custom_mapping_file = []
                # base_dir = ...
                # [tool.fawltydeps.custom_mapping]
                """
            ).splitlines(),
            id="generate_toml_config_with_multiple_pyenvs",
        ),
        pytest.param(
            {},
            ["--install-deps", "--exclude", "foo*", "bar/", "--generate-toml-config"],
            dedent(
                f"""\
                # Copy this TOML section into your pyproject.toml to configure FawltyDeps
                # (default values are commented)
                [tool.fawltydeps]
                # actions = ['check_undeclared', 'check_unused']
                # output_format = 'human_summary'
                # code = ['.']
                # deps = ['.']
                # pyenvs = ['.']
                # ignore_undeclared = []
                # ignore_unused = {sorted(DEFAULT_IGNORE_UNUSED)}
                # deps_parser_choice = ...
                install_deps = true
                exclude = ['bar/', 'foo*']
                # exclude_from = []
                # verbosity = 0
                # custom_mapping_file = []
                # base_dir = ...
                # [tool.fawltydeps.custom_mapping]
                """
            ).splitlines(),
            id="generate_toml_config_with_install_deps",
        ),
        pytest.param(
            {"exclude": ["/foo/bar", "baz/*"]},
            ["--list-sources", "--exclude-from", "my_ignore", "--generate-toml-config"],
            dedent(
                f"""\
                # Copy this TOML section into your pyproject.toml to configure FawltyDeps
                # (default values are commented)
                [tool.fawltydeps]
                actions = ['list_sources']
                # output_format = 'human_summary'
                # code = ['.']
                # deps = ['.']
                # pyenvs = ['.']
                # ignore_undeclared = []
                # ignore_unused = {sorted(DEFAULT_IGNORE_UNUSED)}
                # deps_parser_choice = ...
                # install_deps = false
                exclude = ['/foo/bar', 'baz/*']
                exclude_from = ['my_ignore']
                # verbosity = 0
                # custom_mapping_file = []
                # base_dir = ...
                # [tool.fawltydeps.custom_mapping]
                """
            ).splitlines(),
            id="generate_toml_config_with_list_sources_exclude_and_exclude_from",
        ),
    ],
)
def test_cmdline_args_in_combination_with_config_file(
    config, args, expect, fake_project, setup_fawltydeps_config
):
    # We keep the project itself constant (one undeclared + one unused dep),
    # but we vary the FD configuration directives and command line args
    tmp_path = fake_project(
        imports=["my_requests"],
        declared_deps=["my_pandas"],
    )
    setup_fawltydeps_config(config)
    output, errors, returncode = run_fawltydeps_subprocess(
        "--config-file=pyproject.toml", *args, cwd=tmp_path
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode in {EXIT_SUCCESS, EXIT_UNDECLARED, EXIT_UNUSED}


def test_deps_across_groups_appear_just_once_in_list_deps_detailed(tmp_path):
    deps_data, uniq_deps = pyproject_toml_contents()
    deps_path = tmp_path / "pyproject.toml"
    exp_lines_from_pyproject = [f"{deps_path}: {dep}" for dep in uniq_deps]
    deps_path.write_text(dedent(deps_data))
    output, _returncode = run_fawltydeps_function(
        "--list-deps", "--detailed", f"--deps={deps_path}"
    )
    obs_lines = output.splitlines()
    assert_unordered_equivalence(obs_lines, exp_lines_from_pyproject)


def test_deps_across_groups_appear_just_once_in_order_in_general_detailed(tmp_path):
    deps_data, uniq_deps = pyproject_toml_contents()
    deps_path = tmp_path / "pyproject.toml"
    deps_path.write_text(dedent(deps_data))
    output, _returncode = run_fawltydeps_function("--detailed", f"{tmp_path}")
    obs_lines_absolute = output.splitlines()
    obs_lines_relevant = dropwhile(
        lambda line: not line.startswith(UNUSED_DEPS_OUTPUT_PREFIX), obs_lines_absolute
    )
    next(obs_lines_relevant)  # discard
    unused_deps = [UnusedDependency(name, [Location(deps_path)]) for name in uniq_deps]
    exp_lines = [
        line
        for dep in unused_deps
        for line in f"- {dep.render(detailed=True)}".split("\n")
    ]
    assert list(obs_lines_relevant) == exp_lines


def pyproject_toml_contents():
    data = dedent(
        """
        [tool.poetry.group.data_science.dependencies]
        my_numpy = "^1.21"
        my_pandas = "^1.3"
        matplotlib = "^3.4"

        [tool.poetry.group.web_development.dependencies]
        django = "^4.0"
        fastapi = "^1.5"
        uvicorn = "^0.15"
        my_requests = "^0.21"
        my_pandas = "^1.3"

        [tool.poetry.group.web_scraping.dependencies]
        scrapy = "^2.5"
        requests-html = "^0.10"
        """
    )
    uniq_deps = [
        "django",
        "fastapi",
        "matplotlib",
        "my_numpy",
        "my_pandas",
        "my_requests",
        "requests-html",
        "scrapy",
        "uvicorn",
    ]
    return data, uniq_deps
