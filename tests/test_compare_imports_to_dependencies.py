"""Test the imports to dependencies comparison function."""
import pytest

from fawltydeps.check import calculate_undeclared, calculate_unused
from fawltydeps.settings import Settings

from .utils import test_vectors


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_calculate_undeclared(vector):
    settings = Settings(ignore_undeclared=vector.ignore_undeclared)
    actual = calculate_undeclared(vector.imports, vector.expect_resolved_deps, settings)
    assert actual == vector.expect_undeclared_deps


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_calculate_unused(vector):
    settings = Settings(ignore_unused=vector.ignore_unused)
    actual = calculate_unused(
        vector.imports, vector.declared_deps, vector.expect_resolved_deps, settings
    )
    assert actual == vector.expect_unused_deps
