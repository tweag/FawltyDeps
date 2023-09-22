"""Test core functionality of DirectoryTraversal class."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, List, Optional, Set, Tuple, TypeVar

import pytest

from fawltydeps.dir_traversal import DirectoryTraversal

from .utils import assert_unordered_equivalence

T = TypeVar("T")


@dataclass
class BaseEntry(ABC):
    """Base class for a file system entry used in traversal tests."""

    path: str

    @abstractmethod
    def __call__(self, tmp_path: Path):
        raise NotImplementedError


@dataclass
class File(BaseEntry):
    """A file with optional contents."""

    contents: str = ""

    def __call__(self, tmp_path: Path):
        path = tmp_path / self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.contents)


@dataclass
class Dir(BaseEntry):
    """A directory."""

    def __call__(self, tmp_path: Path):
        path = tmp_path / self.path
        path.mkdir(parents=True)


@dataclass
class RelativeSymlink(BaseEntry):
    """A symlink to a relative path."""

    target: str

    def __call__(self, tmp_path: Path):
        path = tmp_path / self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(self.target)


@dataclass
class AbsoluteSymlink(BaseEntry):
    """A symlink to an absolute path."""

    target: str

    def __call__(self, tmp_path: Path):
        assert tmp_path.is_absolute()
        path = tmp_path / self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(tmp_path / self.target)


@dataclass
class ExpectedTraverseStep(Generic[T]):
    """Expected data for one step of DirectoryTraversal."""

    # All strings are relative to tmp_path
    cur_dir: str
    subdirs: List[str]
    files: List[str]
    attached: List[T]

    def prepare(self, tmp_path: Path) -> Tuple[Path, Set[Path], Set[Path], List[T]]:
        return (
            tmp_path / self.cur_dir,
            {tmp_path / self.cur_dir / d for d in self.subdirs},
            {tmp_path / self.cur_dir / f for f in self.files},
            self.attached,
        )


@dataclass
class DirectoryTraversalVector(Generic[T]):
    """Test vectors for DirectoryTraversal."""

    id: str
    given: List[BaseEntry]
    add: List[Tuple[str, Tuple[T, ...]]] = field(default_factory=lambda: [(".", ())])
    ignore: List[str] = field(default_factory=list)
    expect: List[ExpectedTraverseStep] = field(default_factory=list)
    expect_alternatives: Optional[List[List[ExpectedTraverseStep]]] = None


directory_traversal_vectors: List[DirectoryTraversalVector] = [
    DirectoryTraversalVector(
        "empty_dir",
        given=[],
        expect=[ExpectedTraverseStep(".", [], [], [])],
    ),
    DirectoryTraversalVector(
        "one_file__attach_data",
        given=[File("foo")],
        add=[(".", (123,))],
        expect=[ExpectedTraverseStep(".", [], ["foo"], [123])],
    ),
    DirectoryTraversalVector(
        "one_subdir_plus__attach_data_on_both",
        given=[Dir("sub")],
        add=[(".", (123,)), ("sub", (456,))],
        expect=[
            ExpectedTraverseStep(".", ["sub"], [], [123]),
            ExpectedTraverseStep("sub", [], [], [123, 456]),
        ],
    ),
    DirectoryTraversalVector(
        "one_subdir__attach_two_data_items_on_parent_dir",
        given=[Dir("sub")],
        add=[(".", (123, 456))],
        expect=[
            ExpectedTraverseStep(".", ["sub"], [], [123, 456]),
            ExpectedTraverseStep("sub", [], [], [123, 456]),
        ],
    ),
    DirectoryTraversalVector(
        "one_subdir__attach_data_twice_on_parent_dir",
        given=[Dir("sub")],
        add=[(".", (123,)), (".", (456,))],
        expect=[
            ExpectedTraverseStep(".", ["sub"], [], [123, 456]),
            ExpectedTraverseStep("sub", [], [], [123, 456]),
        ],
    ),
    DirectoryTraversalVector(
        "add_subdir__ignore_parent_with_data__traverse_only_subdir_with_no_data",
        given=[Dir("sub")],
        add=[(".", (123,)), ("sub", ())],
        ignore=["."],
        expect=[ExpectedTraverseStep("sub", [], [], [])],
    ),
    DirectoryTraversalVector(
        "nested_subdir__attach_data_on_some_parents__gets_data_from_grandparents",
        given=[Dir("a/b/c/d")],
        add=[("a/b/c", (123,)), ("a", (456,)), (".", ())],
        expect=[
            ExpectedTraverseStep(".", ["a"], [], []),
            ExpectedTraverseStep("a", ["b"], [], [456]),
            ExpectedTraverseStep("a/b", ["c"], [], [456]),
            ExpectedTraverseStep("a/b/c", ["d"], [], [456, 123]),
            ExpectedTraverseStep("a/b/c/d", [], [], [456, 123]),
        ],
    ),
    DirectoryTraversalVector(
        "symlinks_to_self__are_not_traversed",
        given=[RelativeSymlink("rel_self", "."), AbsoluteSymlink("abs_self", ".")],
        expect=[ExpectedTraverseStep(".", ["rel_self", "abs_self"], [], [])],
    ),
    DirectoryTraversalVector(
        "symlinks_to_parent__are_not_traversed",
        given=[
            RelativeSymlink("sub/rel_parent", ".."),
            AbsoluteSymlink("sub/abs_parent", "."),
        ],
        expect=[
            ExpectedTraverseStep(".", ["sub"], [], []),
            ExpectedTraverseStep("sub", ["rel_parent", "abs_parent"], [], []),
        ],
    ),
    DirectoryTraversalVector(
        "mutual_symlinks__are_traversed_once",
        given=[
            RelativeSymlink("sub1/rel_link_sub2", "../sub2"),
            AbsoluteSymlink("sub2/abs_link_sub1", "sub1"),
        ],
        expect_alternatives=[
            [
                ExpectedTraverseStep(".", ["sub1", "sub2"], [], []),
                ExpectedTraverseStep("sub1", ["rel_link_sub2"], [], []),
                ExpectedTraverseStep("sub2", ["abs_link_sub1"], [], []),
            ],
            [
                ExpectedTraverseStep(".", ["sub1", "sub2"], [], []),
                ExpectedTraverseStep("sub1", ["rel_link_sub2"], [], []),
                ExpectedTraverseStep("sub1/rel_link_sub2", ["abs_link_sub1"], [], []),
            ],
            [
                ExpectedTraverseStep(".", ["sub1", "sub2"], [], []),
                ExpectedTraverseStep("sub2", ["abs_link_sub1"], [], []),
                ExpectedTraverseStep("sub2/abs_link_sub1", ["rel_link_sub2"], [], []),
            ],
        ],
    ),
    DirectoryTraversalVector(
        "relative_symlink_to_dir_elsewhere__is_traversed",
        given=[
            File("elsewhere/file"),
            RelativeSymlink("here/symlink", "../elsewhere"),
        ],
        add=[("here", ())],
        expect=[
            ExpectedTraverseStep("here", ["symlink"], [], []),
            ExpectedTraverseStep("here/symlink", [], ["file"], []),
        ],
    ),
    DirectoryTraversalVector(
        "absolute_symlink_to_dir_elsewhere__is_traversed",
        given=[
            File("elsewhere/file"),
            AbsoluteSymlink("here/symlink", "elsewhere"),
        ],
        add=[("here", ())],
        expect=[
            ExpectedTraverseStep("here", ["symlink"], [], []),
            ExpectedTraverseStep("here/symlink", [], ["file"], []),
        ],
    ),
    DirectoryTraversalVector(
        "dir_and_symlinks_to_dir__is_traversed_only_once",
        given=[
            File("dir/file"),
            RelativeSymlink("rel_link", "./dir"),
            AbsoluteSymlink("abs_link", "dir"),
        ],
        expect_alternatives=[
            [
                ExpectedTraverseStep(".", ["dir", "rel_link", "abs_link"], [], []),
                ExpectedTraverseStep("dir", [], ["file"], []),
            ],
            [
                ExpectedTraverseStep(".", ["dir", "rel_link", "abs_link"], [], []),
                ExpectedTraverseStep("rel_link", [], ["file"], []),
            ],
            [
                ExpectedTraverseStep(".", ["dir", "rel_link", "abs_link"], [], []),
                ExpectedTraverseStep("abs_link", [], ["file"], []),
            ],
        ],
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in directory_traversal_vectors]
)
def test_DirectoryTraversal(vector: DirectoryTraversalVector, tmp_path):
    for entry in vector.given:
        entry(tmp_path)

    traversal: DirectoryTraversal = DirectoryTraversal()
    for path, data_items in vector.add:
        traversal.add(tmp_path / path, *data_items)
    for path in vector.ignore:
        traversal.ignore(tmp_path / path)

    actual = [
        (cur_dir, set(subdirs), set(files), list(data))
        for cur_dir, subdirs, files, data in traversal.traverse()
    ]
    if vector.expect_alternatives is None:  # vector.expect _must_ match
        expect = [step.prepare(tmp_path) for step in vector.expect]
        assert_unordered_equivalence(actual, expect)
    else:  # one of the alternatives must match
        for alternative in vector.expect_alternatives:
            expect = [step.prepare(tmp_path) for step in alternative]
            try:
                assert_unordered_equivalence(actual, expect)
            except AssertionError:  # this alternative failed
                continue  # skip to next alternative
            else:  # this alternative passed
                break  # abort loop and skip below else clause
        else:  # we exhausted all alternatives
            assert False, f"None of the alternatives matched {actual}"


def test_DirectoryTraversal__raises_error__when_adding_missing_dir(tmp_path):
    traversal = DirectoryTraversal()
    with pytest.raises(NotADirectoryError):
        traversal.add(tmp_path / "MISSING")
