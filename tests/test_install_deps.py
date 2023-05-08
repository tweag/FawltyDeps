"""Verify behavior of TemporaryPipInstallResolver."""
import logging

from fawltydeps.packages import (
    IdentityMapping,
    Package,
    TemporaryPipInstallResolver,
    resolve_dependencies,
)


def test_resolve_dependencies_install_deps__via_local_cache(local_pypi):
    debug_info = "Provided by temporary `pip install`"
    actual = resolve_dependencies(
        ["leftpadx", "click"], pyenv_path=None, install_deps=True
    )
    assert actual == {
        "leftpadx": Package(
            "leftpadx", {"leftpad"}, TemporaryPipInstallResolver, debug_info
        ),
        "click": Package("click", {"click"}, TemporaryPipInstallResolver, debug_info),
    }


def test_resolve_dependencies_install_deps__handle_pip_install_failure(
    caplog, local_pypi
):
    # TemporaryPipInstallResolver will handle the inevitable pip install error
    # and return to resolve_dependencies() with the missing package unresolved.
    # For now, IdentityMapping "saves the day" and supplies a Package object.
    # Soon, this should result in an unresolved package error instead.
    caplog.set_level(logging.WARNING)
    actual = resolve_dependencies(
        ["does_not_exist"], pyenv_path=None, install_deps=True
    )
    assert actual == {
        "does_not_exist": Package(
            "does_not_exist", {"does_not_exist"}, IdentityMapping
        ),
    }
    assert all(word in caplog.text for word in ["pip", "install", "does_not_exist"])


def test_resolve_dependencies_install_deps__pip_install_some_packages(
    caplog, local_pypi
):
    debug_info = "Provided by temporary `pip install`"
    caplog.set_level(logging.WARNING)
    actual = resolve_dependencies(
        ["click", "does_not_exist", "leftpadx"], pyenv_path=None, install_deps=True
    )
    # pip install is able to install "leftpadx", but "package_does_not_exist"
    # falls through to IdentityMapping.
    assert actual == {
        "click": Package("click", {"click"}, TemporaryPipInstallResolver, debug_info),
        "does_not_exist": Package(
            "does_not_exist", {"does_not_exist"}, IdentityMapping
        ),
        "leftpadx": Package(
            "leftpadx", {"leftpad"}, TemporaryPipInstallResolver, debug_info
        ),
    }
    assert all(word in caplog.text for word in ["pip", "install", "does_not_exist"])
