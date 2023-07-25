"""Verify behavior of command-line interface.

This is more of an integration test than a unit test, in that we test the
overall behavior of the command line interface, rather than testing our
core exhaustively (which is what the other unit tests are for.
"""

import json
import logging
from dataclasses import dataclass, field
from itertools import dropwhile
from textwrap import dedent
from typing import List

import pytest

from fawltydeps.main import UNUSED_DEPS_OUTPUT_PREFIX, VERBOSE_PROMPT, Analysis, version
from fawltydeps.types import Location, UnusedDependency

from .test_extract_imports_simple import generate_notebook
from .utils import (
    assert_unordered_equivalence,
    run_fawltydeps_function,
    run_fawltydeps_subprocess,
)

logger = logging.getLogger(__name__)


def make_json_settings_dict(**kwargs):
    """
    Create an expected version of Settings.dict(), with customizations.
    """
    settings = {
        "actions": ["check_undeclared", "check_unused"],
        "code": ["."],
        "deps": ["."],
        "pyenvs": [],
        "custom_mapping": None,
        "output_format": "human_summary",
        "ignore_undeclared": [],
        "ignore_unused": [],
        "deps_parser_choice": None,
        "install_deps": False,
        "verbosity": 0,
        "custom_mapping_file": [],
    }
    settings.update(kwargs)
    return settings


@pytest.mark.parametrize(
    "cli_options,expect_output,expect_logs",
    [
        pytest.param(
            ["--detailed", "--verbose"],
            [
                f"<stdin>:{n}: {i}"
                for i, n in [("requests", 4), ("foo", 5), ("numpy", 6)]
            ],
            ["INFO:fawltydeps.extract_imports:Parsing Python code from standard input"],
            id="detailed",
        ),
        pytest.param(
            ["--summary"],
            ["foo", "numpy", "requests", "", VERBOSE_PROMPT],
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

        import requests
        from foo import bar, baz
        import numpy as np
        """
    )

    output, errors, returncode = run_fawltydeps_subprocess(
        "--list-imports", "--code=-", *cli_options, to_stdin=code
    )
    assert output.splitlines() == expect_output
    assert_unordered_equivalence(errors.splitlines(), expect_logs)
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
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--detailed", f"--code={tmp_path}/myfile.py"
    )
    assert output.splitlines() == expect
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
        "settings": make_json_settings_dict(
            actions=["list_imports"],
            code=[f"{tmp_path}/myfile.py"],
            output_format="json",
        ),
        "imports": [
            {
                "name": "requests",
                "source": {"path": f"{tmp_path}/myfile.py", "lineno": 4},
            },
            {"name": "foo", "source": {"path": f"{tmp_path}/myfile.py", "lineno": 5}},
            {"name": "numpy", "source": {"path": f"{tmp_path}/myfile.py", "lineno": 6}},
        ],
        "declared_deps": None,
        "resolved_deps": None,
        "undeclared_deps": None,
        "unused_deps": None,
        "version": version(),
    }
    output, returncode = run_fawltydeps_function(
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
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--detailed", f"--code={tmp_path}/myfile.ipynb"
    )
    assert output.splitlines() == expect
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
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--detailed", f"--code={tmp_path}"
    )
    assert output.splitlines() == expect
    assert returncode == 0


def test_list_imports__from_unsupported_file__fails_with_exit_code_2(tmp_path):
    filepath = tmp_path / "test.NOT_SUPPORTED"
    filepath.write_text("import pandas")
    _output, errors, returncode = run_fawltydeps_subprocess(
        "--list-imports", f"--code={filepath}"
    )
    assert (
        f"Supported formats are .py and .ipynb; Cannot parse code: {filepath}" in errors
    )
    assert returncode == 2


def test_list_imports__from_missing_file__fails_with_exit_code_2(tmp_path):
    missing_path = tmp_path / "MISSING.py"
    _output, errors, returncode = run_fawltydeps_subprocess(
        "--list-imports", f"--code={missing_path}"
    )
    assert f"Code path to parse is neither dir nor file: {missing_path}" in errors
    assert returncode == 2


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
    assert returncode == 0


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
    assert returncode == 0


def test_list_imports__pick_multiple_files_dir_and_code__prints_all_imports(
    project_with_multiple_python_files,
):
    code = dedent(
        """\
        from pathlib import Path
        import platform, sys

        import requests
        from foo import bar, baz
        import numpy as np
        """
    )
    path_code2 = project_with_multiple_python_files / "python_file.py"
    output, returncode = run_fawltydeps_function(
        "--list-imports", "--code", "-", f"{path_code2}", to_stdin=code
    )
    expect = ["django", "requests", "foo", "numpy"]
    assert_unordered_equivalence(output.splitlines()[:-2], expect)
    assert returncode == 0


def test_list_deps_detailed__dir__prints_deps_from_requirements_txt(fake_project):
    tmp_path = fake_project(
        imports=["requests", "pandas"],
        declared_deps=["requests", "pandas"],
    )

    expect = [
        f"{tmp_path}/requirements.txt: pandas",
        f"{tmp_path}/requirements.txt: requests",
    ]
    output, returncode = run_fawltydeps_function(
        "--list-deps", "--detailed", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert returncode == 0


def test_list_deps_json__dir__prints_deps_from_requirements_txt(fake_project):
    tmp_path = fake_project(
        imports=["requests", "pandas"],
        declared_deps=["requests", "pandas"],
    )

    expect = {
        "settings": make_json_settings_dict(
            actions=["list_deps"], deps=[f"{tmp_path}"], output_format="json"
        ),
        "imports": None,
        "declared_deps": [
            {
                "name": "requests",
                "source": {"path": f"{tmp_path}/requirements.txt"},
            },
            {
                "name": "pandas",
                "source": {"path": f"{tmp_path}/requirements.txt"},
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
    assert returncode == 0


def test_list_deps_summary__dir__prints_deps_from_requirements_txt(fake_project):
    tmp_path = fake_project(
        imports=["requests", "pandas"],
        declared_deps=["requests", "pandas"],
    )

    expect = ["pandas", "requests"]
    output, returncode = run_fawltydeps_function("--list-deps", f"--deps={tmp_path}")
    assert output.splitlines()[:-2] == expect
    assert returncode == 0


def test_list_deps__unsupported_file__fails_with_exit_code_2(tmp_path):
    filepath = tmp_path / "test.NOT_SUPPORTED"
    filepath.write_text("pandas\n")

    _output, errors, returncode = run_fawltydeps_subprocess(
        "--list-deps", f"--deps={filepath}"
    )
    assert returncode == 2
    assert f"Parsing given dependencies path isn't supported: {filepath}" in errors


def test_list_deps__missing_path__fails_with_exit_code_2(tmp_path):
    missing_path = tmp_path / "MISSING_PATH"

    _output, errors, returncode = run_fawltydeps_subprocess(
        "--list-deps", f"--deps={missing_path}"
    )
    assert returncode == 2
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
    assert returncode == 0


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
    assert returncode == 0


@dataclass
class ProjectTestVector:
    """Test vectors for FawltyDeps Settings configuration."""

    id: str
    options: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    declares: List[str] = field(default_factory=list)

    expect_output: List[str] = field(default_factory=list)
    expect_logs: List[str] = field(default_factory=list)
    expect_returncode: int = 0


full_success_message = (
    Analysis.success_message(check_undeclared=True, check_unused=True) or ""
)

project_tests_samples = [
    ProjectTestVector(
        id="simple_project_imports_match_dependencies__prints_verbose_option",
        options=["--check", "--code={path}", "--deps={path}"],
        imports=["requests", "pandas"],
        declares=["requests", "pandas"],
        expect_output=[full_success_message],
    ),
    ProjectTestVector(
        id="simple_project_with_missing_deps__reports_undeclared",
        options=["--check", "--detailed", "--code={path}", "--deps={path}"],
        imports=["requests", "pandas"],
        declares=["pandas"],
        expect_output=[
            "These imports appear to be undeclared dependencies:",
            "- 'requests' imported at:",
            "    {path}/code.py:1",
        ],
        expect_returncode=3,
    ),
    ProjectTestVector(
        id="simple_project_with_extra_deps__reports_unused",
        options=["--check", "--detailed", "--code={path}", "--deps={path}"],
        imports=["requests"],
        declares=["requests", "pandas"],
        expect_output=[
            "These dependencies appear to be unused (i.e. not imported):",
            "- 'pandas' declared in:",
            "    {path}/requirements.txt",
        ],
        expect_returncode=4,
    ),
    ProjectTestVector(
        id="simple_project_with_extra_deps__reports_unused_and_undeclared",
        options=["--check", "--detailed", "--code={path}", "--deps={path}"],
        imports=["requests"],
        declares=["pandas"],
        expect_output=[
            "These imports appear to be undeclared dependencies:",
            "- 'requests' imported at:",
            "    {path}/code.py:1",
            "",
            "These dependencies appear to be unused (i.e. not imported):",
            "- 'pandas' declared in:",
            "    {path}/requirements.txt",
        ],
        expect_returncode=3,  # undeclared is more important than unused
    ),
    ProjectTestVector(
        id="simple_project__summary_report_with_verbose_logging",
        options=["--check", "--summary", "--verbose", "--code={path}", "--deps={path}"],
        imports=["requests"],
        declares=["pandas"],
        expect_output=[
            "These imports appear to be undeclared dependencies:",
            "- 'requests'",
            "",
            "These dependencies appear to be unused (i.e. not imported):",
            "- 'pandas'",
            "",
            VERBOSE_PROMPT,
        ],
        expect_logs=[
            "INFO:fawltydeps.extract_imports:Finding Python files under {path}",
            "INFO:fawltydeps.extract_imports:Parsing Python file {path}/code.py",
            "INFO:fawltydeps.packages:'pandas' was not resolved."
            " Assuming it can be imported as 'pandas'.",
        ],
        expect_returncode=3,  # undeclared is more important than unused
    ),
    ProjectTestVector(
        id="simple_project__summary_report_with_quiet_logging",
        options=["--check", "--detailed", "--code={path}", "--deps={path}"],
        imports=["requests"],
        declares=["pandas"],
        expect_output=[
            "These imports appear to be undeclared dependencies:",
            "- 'requests' imported at:",
            "    {path}/code.py:1",
            "",
            "These dependencies appear to be unused (i.e. not imported):",
            "- 'pandas' declared in:",
            "    {path}/requirements.txt",
        ],
        expect_returncode=3,  # undeclared is more important than unused
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
        imports=["requests"],
        declared_deps=["pandas"],
    )

    expect = {
        "settings": make_json_settings_dict(
            code=[f"{tmp_path}"], deps=[f"{tmp_path}"], output_format="json"
        ),
        "imports": [
            {
                "name": "requests",
                "source": {"path": f"{tmp_path}/code.py", "lineno": 1},
            },
        ],
        "declared_deps": [
            {
                "name": "pandas",
                "source": {"path": f"{tmp_path}/requirements.txt"},
            },
        ],
        "resolved_deps": {
            "pandas": {
                "package_name": "pandas",
                "import_names": ["pandas"],
                "resolved_with": "IdentityMapping",
                "debug_info": None,
            }
        },
        "undeclared_deps": [
            {
                "name": "requests",
                "references": [{"path": f"{tmp_path}/code.py", "lineno": 1}],
            },
        ],
        "unused_deps": [
            {
                "name": "pandas",
                "references": [{"path": f"{tmp_path}/requirements.txt"}],
            },
        ],
        "version": version(),
    }
    output, returncode = run_fawltydeps_function(
        "--check", "--json", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert json.loads(output) == expect
    assert returncode == 3  # --json does not affect exit code


def test_check_undeclared__simple_project__reports_only_undeclared(fake_project):
    tmp_path = fake_project(
        imports=["requests"],
        declared_deps=["pandas"],
    )

    expect = [
        "These imports appear to be undeclared dependencies:",
        "- 'requests' imported at:",
        f"    {tmp_path / 'code.py'}:1",
    ]
    output, returncode = run_fawltydeps_function(
        "--check-undeclared",
        "--detailed",
        f"--code={tmp_path}",
        "--deps",
        f"{tmp_path}",
    )
    assert output.splitlines() == expect
    assert returncode == 3


def test_check_unused__simple_project__reports_only_unused(fake_project):
    tmp_path = fake_project(
        imports=["requests"],
        declared_deps=["pandas"],
    )

    expect = [
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas' declared in:",
        f"    {tmp_path / 'requirements.txt'}",
    ]
    output, returncode = run_fawltydeps_function(
        "--check-unused",
        "--detailed",
        f"--code={tmp_path}",
        "--deps",
        f"{tmp_path}",
    )
    assert output.splitlines() == expect
    assert returncode == 4


def test__no_action__defaults_to_check_action(fake_project):
    tmp_path = fake_project(
        imports=["requests"],
        declared_deps=["pandas"],
    )

    expect = [
        "These imports appear to be undeclared dependencies:",
        "- 'requests' imported at:",
        f"    {tmp_path / 'code.py'}:1",
        "",
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas' declared in:",
        f"    {tmp_path / 'requirements.txt'}",
    ]
    output, returncode = run_fawltydeps_function(
        f"--code={tmp_path}", "--detailed", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert returncode == 3


def test__no_options__defaults_to_check_action_in_current_dir(fake_project):
    tmp_path = fake_project(
        imports=["requests"],
        declared_deps=["pandas"],
    )

    expect = [
        "These imports appear to be undeclared dependencies:",
        "- 'requests' imported at:",
        "    code.py:1",
        "",
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas' declared in:",
        "    requirements.txt",
    ]
    expect_logs = []
    output, errors, returncode = run_fawltydeps_subprocess("--detailed", cwd=tmp_path)
    assert output.splitlines() == expect
    assert_unordered_equivalence(errors.splitlines(), expect_logs)
    assert returncode == 3


def test_check__summary__writes_only_names_of_unused_and_undeclared(fake_project):
    tmp_path = fake_project(
        imports=["requests"],
        declared_deps=["pandas"],
    )

    expect = [
        "These imports appear to be undeclared dependencies:",
        "- 'requests'",
        "",
        "These dependencies appear to be unused (i.e. not imported):",
        "- 'pandas'",
        "",
        VERBOSE_PROMPT,
    ]
    output, returncode = run_fawltydeps_function("--check", basepath=tmp_path)
    assert output.splitlines() == expect
    assert returncode == 3


def test_check_detailed__simple_project_in_fake_venv__resolves_imports_vs_deps(
    fake_project,
):
    tmp_path = fake_project(
        imports=["requests"],
        declared_deps=["pandas"],
        # A venv where the "pandas" package provides a "requests" import name
        # should satisfy our comparison
        fake_venvs={".venv": {"pandas": {"requests"}}},
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
    assert returncode == 0


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
    assert returncode == 0


@pytest.mark.parametrize(
    "args,imports,dependencies,expected",
    [
        pytest.param(
            ["--check-unused", "--ignore-unused", "black", "mypy"],
            ["requests"],
            ["black", "mypy"],
            [Analysis.success_message(check_undeclared=False, check_unused=True)],
            id="check_unused_action_on_ignored_unused_dep__outputs_nothing",
        ),
        pytest.param(
            ["--list-deps", "--ignore-unused", "black"],
            [],
            ["black"],
            ["black", "", VERBOSE_PROMPT],
            id="list_deps_action_on_ignored_dep__reports_dep",
        ),
        pytest.param(
            ["--check-undeclared", "--ignore-unused", "isort"],
            ["isort"],
            ["isort"],
            [Analysis.success_message(check_undeclared=True, check_unused=False)],
            id="check_undeclared_action_on_ignored_declared_dep__does_not_report_dep_as_undeclared",
        ),
        pytest.param(
            ["--check-undeclared", "--ignore-undeclared", "black", "mypy"],
            ["black", "mypy"],
            ["numpy"],
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
                "numpy",
                "--ignore-unused",
                "pylint",
                "black",
            ],
            ["isort", "numpy"],
            ["pylint", "black"],
            [Analysis.success_message(check_undeclared=True, check_unused=True)],
            id="check_action_on_ignored__does_not_report_ignored",
        ),
    ],
)
def test_cmdline_on_ignored_undeclared_option(
    args, imports, dependencies, expected, fake_project
):
    tmp_path = fake_project(
        imports=imports,
        declared_deps=dependencies,
    )
    output, returncode = run_fawltydeps_function(*args, basepath=tmp_path)
    assert output.splitlines() == expected
    assert returncode == 0


@pytest.mark.parametrize(
    "config,args,expect",
    [
        pytest.param(
            {},
            [],
            [
                "These imports appear to be undeclared dependencies:",
                "- 'requests'",
                "",
                "These dependencies appear to be unused (i.e. not imported):",
                "- 'pandas'",
                "",
                VERBOSE_PROMPT,
            ],
            id="no_config_no_args__show_summary_of_undeclared_and_unused",
        ),
        pytest.param(
            {"actions": ["list_imports"]},
            [],
            [
                "requests",
                "",
                VERBOSE_PROMPT,
            ],
            id="setting_actions_in_config__changes_default_action",
        ),
        pytest.param(
            {"actions": ["list_imports"]},
            ["--detailed"],
            ["code.py:1: requests"],
            id="combine_actions_in_config_with_detailed_on_command_line",
        ),
        pytest.param(
            {"actions": ["list_imports"], "output_format": "human_detailed"},
            ["--list-deps"],
            ["requirements.txt: pandas"],
            id="override_some_config_directives_on_command_line",
        ),
        pytest.param(
            {"actions": ["list_imports"], "output_format": "human_detailed"},
            ["--summary"],
            [
                "requests",
                "",
                VERBOSE_PROMPT,
            ],
            id="override_output_format_from_config_with_command_line_option",
        ),
        pytest.param(
            {"actions": ["list_imports"], "output_format": "json"},
            ["--detailed", "--deps=foobar", "--generate-toml-config"],
            dedent(
                """\
                # Copy this TOML section into your pyproject.toml to configure FawltyDeps
                # (default values are commented)
                [tool.fawltydeps]
                actions = ['list_imports']
                output_format = 'human_detailed'
                # code = ['.']
                deps = ['foobar']
                # pyenvs = []
                # ignore_undeclared = []
                # ignore_unused = []
                # deps_parser_choice = ...
                # install_deps = false
                # verbosity = 0
                # custom_mapping_file = []
                # [tool.fawltydeps.custom_mapping]
                """
            ).splitlines(),
            id="generate_toml_config_with_combo_of_config_and_cmdline_options",
        ),
        pytest.param(
            {"actions": ["check_undeclared"]},
            ["--pyenv=None", "--generate-toml-config"],
            dedent(
                """\
                # Copy this TOML section into your pyproject.toml to configure FawltyDeps
                # (default values are commented)
                [tool.fawltydeps]
                actions = ['check_undeclared']
                # output_format = 'human_summary'
                # code = ['.']
                # deps = ['.']
                pyenvs = ['None']
                # ignore_undeclared = []
                # ignore_unused = []
                # deps_parser_choice = ...
                # install_deps = false
                # verbosity = 0
                # custom_mapping_file = []
                # [tool.fawltydeps.custom_mapping]
                """
            ).splitlines(),
            id="generate_toml_config_with_a_setting_set_to_str_None",
        ),
        pytest.param(
            {"pyenvs": ["foo", "bar"]},
            ["--pyenv", "baz", "xyzzy", "--generate-toml-config"],
            dedent(
                """\
                # Copy this TOML section into your pyproject.toml to configure FawltyDeps
                # (default values are commented)
                [tool.fawltydeps]
                # actions = ['check_undeclared', 'check_unused']
                # output_format = 'human_summary'
                # code = ['.']
                # deps = ['.']
                pyenvs = ['baz', 'xyzzy']
                # ignore_undeclared = []
                # ignore_unused = []
                # deps_parser_choice = ...
                # install_deps = false
                # verbosity = 0
                # custom_mapping_file = []
                # [tool.fawltydeps.custom_mapping]
                """
            ).splitlines(),
            id="generate_toml_config_with_multiple_pyenvs",
        ),
    ],
)
def test_cmdline_args_in_combination_with_config_file(
    config, args, expect, fake_project, setup_fawltydeps_config
):
    # We keep the project itself constant (one undeclared + one unused dep),
    # but we vary the FD configuration directives and command line args
    tmp_path = fake_project(
        imports=["requests"],
        declared_deps=["pandas"],
    )
    setup_fawltydeps_config(config)
    output, errors, returncode = run_fawltydeps_subprocess(
        "--config-file=pyproject.toml", *args, cwd=tmp_path
    )
    assert output.splitlines() == expect
    assert errors == ""
    assert returncode in {0, 3, 4}


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
        for line in f"- {dep.render(include_references=True)}".split("\n")
    ]
    assert list(obs_lines_relevant) == exp_lines


def pyproject_toml_contents():
    data = dedent(
        """
        [tool.poetry.group.lint.dependencies]
        mypy = "^0.991"
        pylint = "^2.15.8"
        types-setuptools = "^65.6.0.2"

        [tool.poetry.group.format.dependencies]
        black = "^22"
        colorama = "^0.4.6"
        codespell = "^2.2.2"

        [tool.poetry.group.dev.dependencies]
        black = "^22"
        codespell = "^2.2.2"
        colorama = "^0.4.6"
        mypy = "^0.991"
        pylint = "^2.15.8"
        types-setuptools = "^65.6.0.2"
        """
    )
    uniq_deps = (
        "black",
        "codespell",
        "colorama",
        "mypy",
        "pylint",
        "types-setuptools",
    )
    return data, uniq_deps
