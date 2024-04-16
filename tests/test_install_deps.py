"""Verify behavior of TemporaryPipInstallResolver."""

import logging

import pytest

from fawltydeps.packages import (
    Package,
    TemporaryPipInstallResolver,
    resolve_dependencies,
    setup_resolvers,
)
from fawltydeps.types import UnresolvedDependenciesError


def test_resolve_dependencies_install_deps__via_local_cache(local_pypi):  # noqa: ARG001
    debug_info = "Provided by temporary `pip install`"
    actual = resolve_dependencies(
        ["leftpadx", "click"], setup_resolvers(install_deps=True)
    )
    assert actual == {
        "leftpadx": Package(
            "leftpadx", {"leftpad"}, TemporaryPipInstallResolver, debug_info
        ),
        "click": Package("click", {"click"}, TemporaryPipInstallResolver, debug_info),
    }


def test_resolve_dependencies_install_deps__raises_unresolved_error_on_pip_install_failure(
    caplog,
    local_pypi,  # noqa: ARG001
):
    # This tests the case where TemporaryPipInstallResolver encounters the
    # inevitable pip install error and returns to resolve_dependencies()
    # with the missing package unresolved.
    # Since either install_deps or IdentityMapping are the final resolvers,
    # this should raise an `UnresolvedDependenciesError`.
    caplog.set_level(logging.WARNING)

    with pytest.raises(UnresolvedDependenciesError):
        resolve_dependencies(["does_not_exist"], setup_resolvers(install_deps=True))

    assert all(word in caplog.text for word in ["pip", "install", "does_not_exist"])


def test_resolve_dependencies_install_deps__unresolved_error_only_warns_failing_packages(
    caplog,
    local_pypi,  # noqa: ARG001
):
    # When we fail to install _some_ - but not all - packages, the error message
    # should only mention the packages that we failed to install.
    caplog.set_level(logging.WARNING)
    deps = {"click", "does_not_exist", "leftpadx"}

    with pytest.raises(UnresolvedDependenciesError):
        resolve_dependencies(deps, setup_resolvers(install_deps=True))

    assert "Failed to install 'does_not_exist'" in caplog.text
    assert "Failed to install 'click'" not in caplog.text
    assert "Failed to install 'leftpadx'" not in caplog.text


def test_resolve_dependencies_install_deps_on_mixed_packages__raises_unresolved_error(
    caplog,
    local_pypi,  # noqa: ARG001
):
    caplog.set_level(logging.DEBUG)
    deps = {"click", "does_not_exist", "leftpadx"}
    # Attempting to pip install "does_not_exist"
    # will result in an `UnresolvedDependenciesError`.
    with pytest.raises(UnresolvedDependenciesError):
        resolve_dependencies(deps, setup_resolvers(install_deps=True))
    # Attempted to install deps with TemporaryPipInstall
    assert (
        f"Trying to resolve {deps!r} with <fawltydeps.packages.TemporaryPipInstallResolver"
        in caplog.text
    )
