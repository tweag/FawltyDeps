"""Verify graceful failure when we cannot extract imports from Python code."""

import subprocess
from pathlib import Path
from textwrap import dedent
from typing import Optional, Tuple

import pytest


def run_fawltydeps(
    *args: str,
    to_stdin: Optional[str] = None,
    check: bool = True,
    cwd: Optional[Path] = None,
) -> Tuple[str, str]:
    proc = subprocess.run(
        ["fawltydeps"] + list(args),
        input=to_stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=check,
        cwd=cwd,
    )
    return proc.stdout.strip(), proc.stderr.strip()


def test_main__list_imports_from_dash__prints_imports_from_stdin():
    code = dedent(
        """\
        from pathlib import Path
        import platform, sys

        import requests
        from foo import bar, baz
        import numpy as np
        """
    )

    expect = ["foo", "numpy", "pathlib", "platform", "requests", "sys"]
    output, errors = run_fawltydeps("--list-imports", "--code=-", to_stdin=code)
    assert output.splitlines() == expect
    assert errors == ""


def test_main__list_imports_from_file__prints_imports_from_file(tmp_path):
    code = dedent(
        """\
        from pathlib import Path
        import platform, sys

        import requests
        from foo import bar, baz
        import numpy as np
        """
    )
    script = tmp_path / "myfile.py"
    script.write_text(code)

    expect = ["foo", "numpy", "pathlib", "platform", "requests", "sys"]
    output, errors = run_fawltydeps("--list-imports", f"--code={script}")
    assert output.splitlines() == expect
    assert errors == ""


def test_main__list_imports_from_dir__prints_imports_from_py_file_only(tmp_path):
    (tmp_path / "file1.py").write_text(
        dedent(
            """\
            from pathlib import Path
            import platform, sys
            """
        )
    )
    (tmp_path / "file2.NOT_PYTHON").write_text(
        dedent(
            """\
            import requests
            from foo import bar, baz
            import numpy as np
            """
        )
    )

    expect = ["pathlib", "platform", "sys"]
    output, errors = run_fawltydeps("--list-imports", f"--code={tmp_path}")
    assert output.splitlines() == expect
    assert errors == ""


def test_main__list_imports_from_missing_file__fails_with_exit_code_2(tmp_path):
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        run_fawltydeps("--list-imports", f"--code={tmp_path}/MISSING.py")
    assert exc_info.value.returncode == 2


def test_main__list_imports_from_empty_dir__logs_but_extracts_nothing(tmp_path):
    # Enable log level INFO with -v
    output, errors = run_fawltydeps("--list-imports", f"--code={tmp_path}", "-v")
    assert output == ""
    assert f"Parsing Python files under {tmp_path}" in errors


def test_main__list_deps_dir__prints_deps_from_requirements_txt(tmp_path):
    (tmp_path / "file1.py").write_text(
        dedent(
            """\
            from pathlib import Path
            import requests, pandas
            """
        )
    )
    (tmp_path / "requirements.txt").write_text(
        dedent(
            """\
            requests
            pandas
            """
        )
    )

    expect = [
        f"pandas: {tmp_path}/requirements.txt",
        f"requests: {tmp_path}/requirements.txt",
    ]
    output, errors = run_fawltydeps("--list-deps", f"--deps={tmp_path}")
    assert output.splitlines() == expect
    assert errors == ""


# TODO: The following tests need changes inside extract_dependencies


def TODO_test_main__list_deps_missing_dir__fails_with_exit_code_2(tmp_path):
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        run_fawltydeps("--list-deps", f"--deps={tmp_path}/MISSING_DIR")
    assert exc_info.value.returncode == 2


def TODO_test_main__list_deps_empty_dir__verbosely_logs_but_extracts_nothing(tmp_path):
    # Enable log level INFO with -v
    output, errors = run_fawltydeps("--list-deps", f"--deps={tmp_path}", "-v")
    assert output == ""
    assert f"Extracting dependencies from {tmp_path}" in errors


def test_main__check_dir__in_clean_project_prints_nothing(tmp_path):
    (tmp_path / "file1.py").write_text(
        dedent(
            """\
            from pathlib import Path
            import requests, pandas
            """
        )
    )
    (tmp_path / "requirements.txt").write_text(
        dedent(
            """\
            requests
            pandas
            """
        )
    )

    expect = []
    output, errors = run_fawltydeps(
        "--check", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""


def test_main__check_dir__when_missing_deps_reports_undeclared(tmp_path):
    (tmp_path / "file1.py").write_text(
        dedent(
            """\
            from pathlib import Path
            import requests, pandas
            """
        )
    )
    (tmp_path / "requirements.txt").write_text(
        dedent(
            """\
            pandas
            """
        )
    )

    expect = [
        "These imports are not declared as dependencies:",
        "- requests",
    ]
    output, errors = run_fawltydeps(
        "--check", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""


def test_main__check_dir__when_extra_deps_reports_unused(tmp_path):
    (tmp_path / "file1.py").write_text(
        dedent(
            """\
            from pathlib import Path
            import requests
            """
        )
    )
    (tmp_path / "requirements.txt").write_text(
        dedent(
            """\
            requests
            pandas
            """
        )
    )

    expect = [
        "These dependencies are not imported in your code:",
        "- pandas",
    ]
    output, errors = run_fawltydeps(
        "--check", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""


def test_main__check_dir__can_report_both_undeclared_and_unused(tmp_path):
    (tmp_path / "file1.py").write_text(
        dedent(
            """\
            from pathlib import Path
            import requests
            """
        )
    )
    (tmp_path / "requirements.txt").write_text(
        dedent(
            """\
            pandas
            """
        )
    )

    expect = [
        "These imports are not declared as dependencies:",
        "- requests",
        "These dependencies are not imported in your code:",
        "- pandas",
    ]
    output, errors = run_fawltydeps(
        "--check", f"--code={tmp_path}", f"--deps={tmp_path}"
    )
    assert output.splitlines() == expect
    assert errors == ""


def test_main__no_action_specified__defaults_to_check_action(tmp_path):
    (tmp_path / "file1.py").write_text(
        dedent(
            """\
            from pathlib import Path
            import requests
            """
        )
    )
    (tmp_path / "requirements.txt").write_text(
        dedent(
            """\
            pandas
            """
        )
    )

    expect = [
        "These imports are not declared as dependencies:",
        "- requests",
        "These dependencies are not imported in your code:",
        "- pandas",
    ]
    output, errors = run_fawltydeps(f"--code={tmp_path}", f"--deps={tmp_path}")
    assert output.splitlines() == expect
    assert errors == ""


def test_main__no_options__defaults_to_check_action_in_current_dir(tmp_path):
    (tmp_path / "file1.py").write_text(
        dedent(
            """\
            from pathlib import Path
            import requests
            """
        )
    )
    (tmp_path / "requirements.txt").write_text(
        dedent(
            """\
            pandas
            """
        )
    )

    expect = [
        "These imports are not declared as dependencies:",
        "- requests",
        "These dependencies are not imported in your code:",
        "- pandas",
    ]
    output, errors = run_fawltydeps(cwd=tmp_path)
    assert output.splitlines() == expect
    assert errors == ""
