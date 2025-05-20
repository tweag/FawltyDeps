"""Test the imports to dependencies comparison function."""

import logging

import pytest

from fawltydeps.check import calculate_undeclared, calculate_unused, is_ignored
from fawltydeps.settings import Settings

from .utils import test_vectors

logger = logging.getLogger(__name__)


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_calculate_undeclared(vector):
    settings = Settings(ignore_undeclared=vector.ignore_undeclared)
    logger.info(f"imports: {vector.imports!r}")
    logger.info(f"declared_deps: {vector.declared_deps!r}")
    logger.info(f"resolver: {vector.resolver!r}")
    logger.info(f"resolved_deps: {vector.expect_resolved_deps!r}")
    actual = calculate_undeclared(
        imports=vector.imports,
        resolved_deps=vector.expect_resolved_deps,
        resolvers=[vector.resolver] if vector.resolver is not None else [],
        settings=settings,
    )
    assert actual == vector.expect_undeclared_deps


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_calculate_unused(vector):
    settings = Settings(ignore_unused=vector.ignore_unused)
    logger.info(f"imports: {vector.imports!r}")
    logger.info(f"declared_deps: {vector.declared_deps!r}")
    logger.info(f"resolved_deps: {vector.expect_resolved_deps!r}")
    actual = calculate_unused(
        imports=vector.imports,
        declared_deps=vector.declared_deps,
        resolved_deps=vector.expect_resolved_deps,
        settings=settings,
    )
    assert actual == vector.expect_unused_deps


@pytest.mark.parametrize(
    ("name", "ignore_set", "expect"),
    [
        pytest.param(
            "baz",
            {"bar", "baz"},
            True,
            id="verbatim match",
        ),
        pytest.param(
            "foo",
            {"bar", "baz"},
            False,
            id="simple non-match",
        ),
        pytest.param(
            "pytest-foo",
            {"bar", "baz", "pytest"},
            False,
            id="no automatic prefix match",
        ),
        pytest.param(
            "pytest-foo",
            {"bar", "baz", "pytest-*"},
            True,
            id="matching wildcard suffix",
        ),
        pytest.param(
            "pytest-foo",
            {"bar", "baz", "*-foo"},
            True,
            id="matching wildcard prefix",
        ),
        pytest.param(
            "pytest-foo",
            {"*"},
            True,
            id="match everything",
        ),
        pytest.param(
            "pytest-foo",
            {"*test-*"},
            True,
            id="matching multi-wildcard",
        ),
        pytest.param(
            "pytestfoo",
            {"*test-*"},
            False,
            id="non-matching multi-wildcard",
        ),
        pytest.param(
            "pytest-foo",
            {"py?test-*", "p?test-*", "p[xyz]test-*", "{py,foo}test-*"},
            False,
            id="do not accept other potential wildcard syntaxes",
        ),
    ],
)
def test_is_ignored(name, ignore_set, expect):
    assert is_ignored(name, ignore_set) == expect
