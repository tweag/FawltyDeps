"""Test various ways to invoke the fawltydeps application."""

import subprocess
import sys

import pytest

from fawltydeps.main import Analysis, version

from .utils import run_fawltydeps_function, run_fawltydeps_subprocess

pytestmark = pytest.mark.integration


def run_package_main(*args: str) -> tuple[str, int]:
    proc = subprocess.run(
        [sys.executable, "-m", "fawltydeps", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip(), proc.returncode


invocation_methods = [
    pytest.param(
        run_fawltydeps_subprocess,
        id="via command-line entry point: `fawltydeps ...`",
    ),
    pytest.param(
        run_package_main,
        id="via package.__main__: `python -m fawltydeps ...`",
    ),
    pytest.param(
        run_fawltydeps_function,
        id="via main() function: `fawltydeps.main.main([...])`",
    ),
]


@pytest.mark.parametrize("run_fawltydeps", invocation_methods)
def test_invocation_with_version(run_fawltydeps):
    if run_fawltydeps is run_fawltydeps_function:
        pytest.skip("run_fawltydeps_function() does not capture --version output")
    output, *_, exit_code = run_fawltydeps("--version")
    assert output == f"FawltyDeps v{version()}"
    assert exit_code == 0


@pytest.mark.parametrize("run_fawltydeps", invocation_methods)
def test_invocation_with_help(run_fawltydeps):
    if run_fawltydeps is run_fawltydeps_function:
        pytest.skip("run_fawltydeps_function() does not capture --help output")
    output, *_, exit_code = run_fawltydeps("--help")
    assert output.startswith("usage: fawltydeps")
    assert exit_code == 0


@pytest.mark.parametrize("run_fawltydeps", invocation_methods)
def test_invocation_in_empty_dir(run_fawltydeps, tmp_path):
    output, *_, exit_code = run_fawltydeps(str(tmp_path))
    assert output == Analysis.success_message(check_undeclared=True, check_unused=True)
    assert exit_code == 0
