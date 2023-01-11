import hashlib
from pathlib import Path
from typing import Iterable

import nox

python_versions = ["3.7", "3.8", "3.9", "3.10", "3.11"]


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
        session.install(".")


@nox.session(python=python_versions)
def tests(session):
    install_groups(session, include=["test"])
    session.run("pytest", "-x", "--log-level=debug", *session.posargs)


@nox.session(python=python_versions)
def integration_tests(session):
    install_groups(session, include=["test"])
    session.run("pytest", "-x", "-m", "integration", *session.posargs)


@nox.session(python=python_versions)
def lint(session):
    install_groups(session, include=["lint"], include_self=False)
    session.run("mypy")
    session.run("pylint", "fawltydeps")
    session.run(
        "pylint",
        "--disable=missing-function-docstring,invalid-name,redefined-outer-name",
        "tests",
    )


@nox.session
def format(session):
    install_groups(session, include=["format"], include_self=False)
    session.run("codespell", "--enable-colors")
    session.run("isort", "fawltydeps", "tests", "--check", "--diff", "--color")
    session.run("black", ".", "--check", "--diff", "--color")


@nox.session
def reformat(session):
    install_groups(session, include=["format"], include_self=False)
    session.run("codespell", "--write-changes")
    session.run("isort", "fawltydeps", "tests")
    session.run("black", ".")
