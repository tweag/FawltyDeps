"""Test the imports to dependencies comparison function."""

import logging

import pytest

from fawltydeps.check import calculate_undeclared, calculate_unused
from fawltydeps.settings import Settings

from .utils import test_vectors

logger = logging.getLogger(__name__)


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_calculate_undeclared(vector):
    settings = Settings(ignore_undeclared=vector.ignore_undeclared)
    logger.info(f"imports: {vector.imports!r}")
    logger.info(f"declared_deps: {vector.declared_deps!r}")
    logger.info(f"resolved_deps: {vector.expect_resolved_deps!r}")
    actual = calculate_undeclared(vector.imports, vector.expect_resolved_deps, settings)
    assert actual == vector.expect_undeclared_deps


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_calculate_unused(vector):
    settings = Settings(ignore_unused=vector.ignore_unused)
    logger.info(f"imports: {vector.imports!r}")
    logger.info(f"declared_deps: {vector.declared_deps!r}")
    logger.info(f"resolved_deps: {vector.expect_resolved_deps!r}")
    actual = calculate_unused(
        vector.imports, vector.declared_deps, vector.expect_resolved_deps, settings
    )
    assert actual == vector.expect_unused_deps
