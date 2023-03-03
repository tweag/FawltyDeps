"""Verify behavior of our basic types."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from fawltydeps.types import (
    DeclaredDependency,
    DependenciesMapping,
    Location,
    Package,
    ParsedImport,
)

testdata = {  # Test ID -> (Location args, expected string representation, sort order)
    # First arg must be a Path, or "<stdin>"
    "nothing": (("<stdin>",), "<stdin>", 111),
    "abs_path": ((Path("/foo/bar"),), "/foo/bar", 211),
    "rel_path": ((Path("foo"),), "foo", 311),
    # Second arg refers to notebook cell, and is rendered in [square brackets]
    "no_path_cell": (("<stdin>", 1), "<stdin>[1]", 121),
    "abs_path_cell": ((Path("/foo/bar"), 2), "/foo/bar[2]", 221),
    "rel_path_cell": ((Path("foo"), 3), "foo[3]", 321),
    # Third arg is line number, and is prefixed by colon
    "no_path_cell_line": (("<stdin>", 1, 2), "<stdin>[1]:2", 122),
    "abs_path_cell_line": ((Path("/foo/bar"), 2, 3), "/foo/bar[2]:3", 222),
    "rel_path_cell_line": ((Path("foo"), 3, 4), "foo[3]:4", 322),
    # Cell number is omitted for non-notebooks.
    "no_path_line": (("<stdin>", None, 2), "<stdin>:2", 112),
    "abs_path_line": ((Path("/foo/bar"), None, 3), "/foo/bar:3", 212),
    "rel_path_line": ((Path("foo"), None, 4), "foo:4", 312),
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
    assert expect == actual


def test_location__numbers_are_sorted_numerically():
    pre_sorted = [
        Location(Path("foo"), 9, 5),
        Location(Path("foo"), 9, 22),
        Location(Path("foo"), 11, 5),
        Location(Path("foo"), 11, 22),
    ]
    post_sorted = sorted(pre_sorted)
    assert pre_sorted == post_sorted


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
    loc = Location(Path("foo.py"))
    assert str(loc) == "foo.py"
    loc2 = loc.supply(lineno=17)
    assert str(loc2) == "foo.py:17"
    loc3 = loc2.supply(cellno=3)
    assert str(loc3) == "foo.py[3]:17"

    # Order of supply calls does not matter as long as result is the same.
    loc4 = loc.supply(cellno=3).supply(lineno=17)
    assert loc3 == loc4


def test_location_is_immutable():
    loc = Location(Path("foo.py"))
    with pytest.raises(FrozenInstanceError):
        loc.cellno = 3
    loc2 = Location("<stdin>", 12, 34)
    with pytest.raises(FrozenInstanceError):
        loc2.path += "foo"
    with pytest.raises(FrozenInstanceError):
        loc2.lineno += 5


def test_parsedimport_is_immutable():
    pi = ParsedImport("foo_module", Location(Path("foo.py")))
    with pytest.raises(FrozenInstanceError):
        pi.name = "bar_module"
    with pytest.raises(FrozenInstanceError):
        pi.source = pi.source.supply(lineno=123)


def test_declareddependency_is_immutable():
    dd = DeclaredDependency("foo_package", Location(Path("requirements.txt")))
    with pytest.raises(FrozenInstanceError):
        dd.name = "bar_package"
    with pytest.raises(FrozenInstanceError):
        dd.source = dd.source.supply(lineno=123)


def test_package__empty_package__matches_nothing():
    p = Package("foobar")  # no mappings
    assert p.package_name == "foobar"
    assert not p.is_used(["foobar"])


@pytest.mark.parametrize(
    "package_name,matching_imports,non_matching_imports",
    [
        pytest.param(
            "foobar",
            ["foobar", "and", "other", "names"],
            ["only", "other", "names", "foo_bar", "Foobar", "FooBar", "FOOBAR"],
            id="simple_lowercase_name__matches_itself_only",
        ),
        pytest.param(
            "FooBar",
            ["foobar", "and", "other", "names"],
            ["only", "other", "names", "foo_bar", "Foobar", "FooBar", "FOOBAR"],
            id="mixed_case_name__matches_lowercase_only",
        ),
        pytest.param(
            "typing-extensions",
            ["typing_extensions", "and", "other", "names"],
            ["typing-extensions", "typingextensions"],
            id="name_with_hyphen__matches_name_with_underscore_only",
        ),
        pytest.param(
            "Foo-Bar",
            ["foo_bar", "and", "other", "names"],
            ["foo-bar", "Foobar", "FooBar", "FOOBAR"],
            id="weird_name__matches_normalized_name_only",
        ),
    ],
)
def test_package__identity_mapping(
    package_name, matching_imports, non_matching_imports
):
    p = Package.identity_mapping(package_name)
    assert p.package_name == package_name  # package name is not normalized
    assert p.is_used(matching_imports)
    assert not p.is_used(non_matching_imports)


@pytest.mark.parametrize(
    "package_name,import_names,matching_imports,non_matching_imports",
    [
        pytest.param(
            "foobar",
            ["foobar"],
            ["foobar", "and", "other", "names"],
            ["only", "other", "names", "foo_bar", "Foobar", "FooBar", "FOOBAR"],
            id="simple_name_mapped_to_itself__matches_itself_only",
        ),
        pytest.param(
            "FooBar",
            ["FooBar"],
            ["FooBar", "and", "other", "names"],
            ["only", "other", "names", "foo_bar", "foobar", "FOOBAR"],
            id="mixed_case_name_mapped_to_itself__matches_exact_spelling_only",
        ),
        pytest.param(
            "typing-extensions",
            ["typing_extensions"],
            ["typing_extensions", "and", "other", "names"],
            ["typing-extensions", "typingextensions"],
            id="hyphen_name_mapped_to_underscore_name__matches_only_underscore_name",
        ),
        pytest.param(
            "Foo-Bar",
            ["blorp"],
            ["blorp", "and", "other", "names"],
            ["Foo-Bar", "foo-bar", "foobar", "FooBar", "FOOBAR", "Blorp", "BLORP"],
            id="weird_name_mapped_diff_name__matches_diff_name_only",
        ),
        pytest.param(
            "foobar",
            ["foo", "bar", "baz"],
            ["foo", "and", "other", "names"],
            ["foobar", "and", "other", "names"],
            id="name_with_three_imports__matches_first_import",
        ),
        pytest.param(
            "foobar",
            ["foo", "bar", "baz"],
            ["bar", "and", "other", "names"],
            ["foobar", "and", "other", "names"],
            id="name_with_three_imports__matches_second_import",
        ),
        pytest.param(
            "foobar",
            ["foo", "bar", "baz"],
            ["baz", "and", "other", "names"],
            ["foobar", "and", "other", "names"],
            id="name_with_three_imports__matches_third_import",
        ),
    ],
)
def test_package__local_env_mapping(
    package_name, import_names, matching_imports, non_matching_imports
):
    p = Package(package_name)
    p.add_import_names(*import_names, mapping=DependenciesMapping.LOCAL_ENV)
    assert p.package_name == package_name  # package name is not normalized
    assert p.is_used(matching_imports)
    assert not p.is_used(non_matching_imports)


def test_package__both_mappings():
    p = Package.identity_mapping("FooBar")
    import_names = ["foo", "bar", "baz"]
    p.add_import_names(*import_names, mapping=DependenciesMapping.LOCAL_ENV)
    assert p.package_name == "FooBar"  # package name is not normalized
    assert p.is_used(["foobar"])  # but identity-mapped import name _is_.
    assert p.is_used(["foo"])
    assert p.is_used(["bar"])
    assert p.is_used(["baz"])
    assert not p.is_used(["fooba"])
    assert not p.is_used(["foobarbaz"])
    assert p.mappings == {
        DependenciesMapping.IDENTITY: {"foobar"},
        DependenciesMapping.LOCAL_ENV: {"foo", "bar", "baz"},
    }
    assert p.import_names == {"foobar", "foo", "bar", "baz"}
