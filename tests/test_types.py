"""Verify behavior of our basic types."""

from pathlib import Path

import pytest

from fawltydeps.types import Location

testdata = {  # Test ID -> (Location args, expected string representation, sort order)
    # The sort order below reveals that "None" sorts before "PosixPath(...)",
    # but after ASCII digits. In practice this does not matter, as we expect
    # Location objects in the same process to have the ~same members specified.
    #
    # First arg must be a Path, or "<stdin>"
    "nothing": (("<stdin>",), "<stdin>", 111),
    "abs_path": ((Path("/foo/bar"),), "/foo/bar", 211),
    "rel_path": ((Path("foo"),), "foo", 311),
    # Second arg refers to notebook cell, and is rendered in [square brackets]
    "no_path_cell": (("<stdin>", 1), "<stdin>[1]", 101),
    "abs_path_cell": ((Path("/foo/bar"), 2), "/foo/bar[2]", 201),
    "rel_path_cell": ((Path("foo"), 3), "foo[3]", 301),
    # Third arg is line number, and is prefixed by colon
    "no_path_cell_line": (("<stdin>", 1, 2), "<stdin>[1]:2", 100),
    "abs_path_cell_line": ((Path("/foo/bar"), 2, 3), "/foo/bar[2]:3", 200),
    "rel_path_cell_line": ((Path("foo"), 3, 4), "foo[3]:4", 300),
    # Cell number is omitted for non-notebooks.
    "no_path_line": (("<stdin>", None, 2), "<stdin>:2", 110),
    "abs_path_line": ((Path("/foo/bar"), None, 3), "/foo/bar:3", 210),
    "rel_path_line": ((Path("foo"), None, 4), "foo:4", 310),
}


@pytest.mark.parametrize(
    "args,string,_", [pytest.param(*data, id=key) for key, data in testdata.items()]
)
def test_location__str(args, string, _):
    assert str(Location(*args)) == string


def test_location__sorting():
    # Sort testdata by sort order, then construct Location objects (in-order)
    expect = [
        Location(*args) for args, *_ in sorted(testdata.values(), key=lambda t: t[2])
    ]
    # Create Location objects (unordered), and then sort the objects themselves
    actual = sorted([Location(*args) for args, *_ in testdata.values()])

    assert actual == expect


def test_location__hashable_and_unique():
    # Use all objects in 'testdata' as keys - and then values - in a dict.
    # Verify that the dict has the same size as the number of entries in
    # 'testdata'. In other words that individual instances in testdata are
    # considered non-equal. Then verify that keys and corresponding values are
    # equal, i.e. that Location instances constructed from the same args
    # are considered equal.
    test_dict = {Location(*args): True for args, *_ in testdata.values()}
    for args, *_ in testdata.values():
        loc = Location(*args)
        test_dict[loc] = loc  # reset {loc: True} to {loc: loc}

    assert len(test_dict) == len(testdata)
    assert all(k == v for k, v in test_dict.items())


def test_location__supply_to_add_additional_info():
    loc = Location("foo.py")
    assert str(loc) == "foo.py"
    loc2 = loc.supply(lineno=17)
    assert str(loc2) == "foo.py:17"
    loc3 = loc2.supply(cellno=3)
    assert str(loc3) == "foo.py[3]:17"

    # Order of supply calls does not matter as long as result is the same.
    loc4 = loc.supply(cellno=3).supply(lineno=17)
    assert loc3 == loc4
