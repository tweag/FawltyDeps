import hashlib
import os
from pathlib import Path
from typing import Iterable

import nox

python_versions = ["3.7", "3.8", "3.9", "3.10", "3.11", "3.12"]


def patch_binaries_if_needed(session: nox.Session, venv_dir: str) -> None:
    """If we are on Nix, auto-patch any binaries under `venv_dir`.

    Detect if we are running under Nix, and auto-patch any pre-built binaries
    that were just installed into the Nox virtualenv.
    """
    build_inputs = os.environ.get("buildInputs", "")  # noqa: SIM112
    if "auto-patchelf-hook" not in build_inputs:
        return

    # We want to invoke autoPatchelf, but it is a shell function in the
    # surrounding Nix shell, and thus not directly available to session.run().
    # However, we can invoke nix-shell and tell it to run autoPathelf for us:
    argv = ["nix-shell", "--run", f"autoPatchelf {venv_dir}"]
    session.run(*argv, silent=True, external=True)


def install_groups(
    session: nox.Session,
    *,
    include: Iterable[str] = (),
    exclude: Iterable[str] = (),
    include_self: bool = True,
) -> None:
    """Install Poetry dependency groups

    This function installs the given dependency groups into the session's
    virtual environment. When 'include_self' is true (the default), the
    function also installs this package (".") and its default dependencies.

    We cannot use `poetry install` directly here, because it ignores the
    session's virtualenv and installs into Poetry's own virtualenv. Instead, we
    use `poetry export` with suitable options to generate a requirements.txt
    file which we can then pass to session.install().

    Auto-skip the `poetry export` step if the poetry.lock file is unchanged
    since the last time this session was run.
    """
    if isinstance(session.virtualenv, nox.virtualenv.PassthroughEnv):
        session.warn(
            "Running outside a Nox virtualenv! We will skip installation here, "
            "and simply assume that the necessary dependency groups have "
            "already been installed by other means!"
        )
        return

    lockdata = Path("poetry.lock").read_bytes()
    digest = hashlib.blake2b(lockdata).hexdigest()
    requirements_txt = Path(session.cache_dir, session.name, "reqs_from_poetry.txt")
    hashfile = requirements_txt.with_suffix(".hash")

    if not hashfile.is_file() or hashfile.read_text() != digest:
        requirements_txt.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            "poetry",
            "export",
            "--format=requirements.txt",
            f"--output={requirements_txt}",
        ]
        if include:
            option = "only" if not include_self else "with"
            argv.append(f"--{option}={','.join(include)}")
        if exclude:
            argv.append(f"--without={','.join(exclude)}")
        session.run_always(*argv, external=True)
        hashfile.write_text(digest)

    session.install("-r", str(requirements_txt))
    if include_self:
        session.install("-e", ".")

    if not session.virtualenv._reused:  # noqa: SLF001
        patch_binaries_if_needed(session, session.virtualenv.location)


@nox.session(python=python_versions)
def tests(session):
    install_groups(session, include=["test"])
    session.run(
        "pytest",
        "-x",
        "--log-level=debug",
        "--durations=10",
        "--hypothesis-show-statistics",
        *session.posargs,
    )


@nox.session(python=python_versions)
def integration_tests(session):
    install_groups(session, include=["test"])
    session.run("pytest", "-x", "-m", "integration", "--durations=10", *session.posargs)


@nox.session(python=python_versions)
def self_test(session):
    # Install all optional dependency groups for a self test
    install_groups(session, include=["nox", "test", "lint", "format", "dev"])
    session.run("fawltydeps")


@nox.session
def lint(session):
    install_groups(session, include=["lint"])
    session.run("mypy")
    session.run("ruff", "check", ".")


@nox.session
def format(session):  # noqa: A001
    install_groups(session, include=["format"], include_self=False)
    session.run("codespell", "--enable-colors")
    session.run("ruff", "format", "--diff", ".")


@nox.session
def reformat(session):
    install_groups(session, include=["format"], include_self=False)
    session.run("codespell", "--write-changes")
    session.run("ruff", "format", ".")
