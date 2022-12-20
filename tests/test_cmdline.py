"""Verify graceful failure when we cannot extract imports from Python code."""

import subprocess
from textwrap import dedent
from typing import Optional, Tuple

import pytest


def run_fawltydeps(
    *args: str, to_stdin: Optional[str] = None, check: bool = True
) -> Tuple[str, str]:
    proc = subprocess.run(
        ["fawltydeps"] + list(args),
        input=to_stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=check,
    )
    return proc.stdout.strip(), proc.stderr.strip()


def test_main__pass_dash__prints_imports_extracted_from_stdin():
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
    output, errors = run_fawltydeps("--code=-", to_stdin=code)
    assert output.splitlines() == expect
    assert errors == ""


def test_main__pass_file__prints_imports_extracted_from_file(tmp_path):
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
    output, errors = run_fawltydeps(f"--code={script}")
    assert output.splitlines() == expect
    assert errors == ""


def test_main__pass_dir__prints_imports_extracted_from_py_file_only(tmp_path):
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
    output, errors = run_fawltydeps(f"--code={tmp_path}")
    assert output.splitlines() == expect
    assert errors == ""


def test_main__pass_missing_file__fails_with_exit_code_2(tmp_path):
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        run_fawltydeps(f"--code={tmp_path}/MISSING.py")
    assert exc_info.value.returncode == 2


def test_main__pass_empty_dir_verbosely__logs_but_extracts_nothing(tmp_path):
    # Enable log level INFO with --verbose
    output, errors = run_fawltydeps(f"--code={tmp_path}", "--verbose")
    assert output == ""
    assert f"Parsing Python files under {tmp_path}" in errors
