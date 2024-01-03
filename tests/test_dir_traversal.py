"""Test core functionality of DirectoryTraversal class."""
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, List, Optional, Tuple, TypeVar, Union

import pytest

from fawltydeps.dir_traversal import DirectoryTraversal, TraversalStep

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
    dir: str
    subdirs: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    attached: List[T] = field(default_factory=list)

    def prepare(self, tmp_path: Path) -> TraversalStep:
        return TraversalStep(
            tmp_path / self.dir,
            frozenset(tmp_path / self.dir / d for d in self.subdirs),
            frozenset(tmp_path / self.dir / f for f in self.files),
            self.attached,
        )


@dataclass(frozen=True)
class AddCall(Generic[T]):
    """Arguments for a call to DirectoryTraversal.add()."""

    path: Union[Path, str]
    attach: Tuple[T, ...] = ()


@dataclass(frozen=True)
class DirectoryTraversalVector(Generic[T]):
    """Test vectors for DirectoryTraversal."""

    id: str
    given: List[BaseEntry]
    add: List[AddCall] = field(default_factory=lambda: [AddCall(path=".")])
    skip_dirs: List[str] = field(default_factory=list)
    expect: List[ExpectedTraverseStep] = field(default_factory=list)
    expect_alternatives: Optional[List[List[ExpectedTraverseStep]]] = None


directory_traversal_vectors: List[DirectoryTraversalVector] = [
    DirectoryTraversalVector(
        "empty_dir",
        given=[],
        expect=[ExpectedTraverseStep(".")],
    ),
    DirectoryTraversalVector(
        "one_file__attach_data",
        given=[File("foo")],
        add=[AddCall(path=".", attach=(123,))],
        expect=[ExpectedTraverseStep(".", files=["foo"], attached=[123])],
    ),
    DirectoryTraversalVector(
        "one_subdir_plus__attach_data_on_both",
        given=[Dir("sub")],
        add=[AddCall(path=".", attach=(123,)), AddCall(path="sub", attach=(456,))],
        expect=[
            ExpectedTraverseStep(".", subdirs=["sub"], attached=[123]),
            ExpectedTraverseStep("sub", attached=[123, 456]),
        ],
    ),
    DirectoryTraversalVector(
        "one_subdir__attach_two_data_items_on_parent_dir",
        given=[Dir("sub")],
        add=[AddCall(path=".", attach=(123, 456))],
        expect=[
            ExpectedTraverseStep(".", subdirs=["sub"], attached=[123, 456]),
            ExpectedTraverseStep("sub", attached=[123, 456]),
        ],
    ),
    DirectoryTraversalVector(
        "one_subdir__attach_data_twice_on_parent_dir",
        given=[Dir("sub")],
        add=[AddCall(path=".", attach=(123,)), AddCall(path=".", attach=(456,))],
        expect=[
            ExpectedTraverseStep(".", subdirs=["sub"], attached=[123, 456]),
            ExpectedTraverseStep("sub", attached=[123, 456]),
        ],
    ),
    DirectoryTraversalVector(
        "add_subdir__skip_parent_with_data__traverse_only_subdir_with_no_data",
        given=[Dir("sub")],
        add=[AddCall(path=".", attach=(123,)), AddCall(path="sub")],
        skip_dirs=["."],
        expect=[ExpectedTraverseStep("sub")],
    ),
    DirectoryTraversalVector(
        "nested_subdir__attach_data_on_some_parents__gets_data_from_grandparents",
        given=[Dir("a/b/c/d")],
        add=[
            AddCall(path="a/b/c", attach=(123,)),
            AddCall(path="a", attach=(456,)),
            AddCall(path="."),
        ],
        expect=[
            ExpectedTraverseStep(".", subdirs=["a"]),
            ExpectedTraverseStep("a", subdirs=["b"], attached=[456]),
            ExpectedTraverseStep(str(Path("a", "b")), subdirs=["c"], attached=[456]),
            ExpectedTraverseStep(
                str(Path("a", "b", "c")), subdirs=["d"], attached=[456, 123]
            ),
            ExpectedTraverseStep(str(Path("a", "b", "c", "d")), attached=[456, 123]),
        ],
    ),
    DirectoryTraversalVector(
        "symlinks_to_self__are_not_traversed",
        given=[RelativeSymlink("rel_self", "."), AbsoluteSymlink("abs_self", ".")],
        expect=[ExpectedTraverseStep(".", subdirs=["rel_self", "abs_self"])],
    ),
    DirectoryTraversalVector(
        "symlinks_to_parent__are_not_traversed",
        given=[
            RelativeSymlink(os.path.join("sub", "rel_parent"), ".."),
            AbsoluteSymlink(os.path.join("sub", "abs_parent"), "."),
        ],
        expect=[
            ExpectedTraverseStep(".", subdirs=["sub"]),
            ExpectedTraverseStep("sub", subdirs=["rel_parent", "abs_parent"]),
        ],
    ),
    DirectoryTraversalVector(
        "mutual_symlinks__are_traversed_once",
        given=[
            RelativeSymlink(
                os.path.join("sub1", "rel_link_sub2"), os.path.join("..", "sub2")
            ),
            AbsoluteSymlink(os.path.join("sub2", "abs_link_sub1"), "sub1"),
        ],
        expect_alternatives=[
            [
                ExpectedTraverseStep(".", subdirs=["sub1", "sub2"]),
                ExpectedTraverseStep("sub1", subdirs=["rel_link_sub2"]),
                ExpectedTraverseStep("sub2", subdirs=["abs_link_sub1"]),
            ],
            [
                ExpectedTraverseStep(".", subdirs=["sub1", "sub2"]),
                ExpectedTraverseStep("sub1", subdirs=["rel_link_sub2"]),
                ExpectedTraverseStep(
                    str(Path("sub1", "rel_link_sub2")), subdirs=["abs_link_sub1"]
                ),
            ],
            [
                ExpectedTraverseStep(".", subdirs=["sub1", "sub2"]),
                ExpectedTraverseStep("sub2", subdirs=["abs_link_sub1"]),
                ExpectedTraverseStep(
                    str(Path("sub2", "abs_link_sub1")), subdirs=["rel_link_sub2"]
                ),
            ],
        ],
    ),
    DirectoryTraversalVector(
        "relative_symlink_to_dir_elsewhere__is_traversed",
        given=[
            File(os.path.join("elsewhere", "file")),
            RelativeSymlink(
                os.path.join("here", "symlink"), os.path.join("..", "elsewhere")
            ),
        ],
        add=[AddCall(path="here")],
        expect=[
            ExpectedTraverseStep("here", subdirs=["symlink"]),
            ExpectedTraverseStep(str(Path("here", "symlink")), files=["file"]),
        ],
    ),
    DirectoryTraversalVector(
        "absolute_symlink_to_dir_elsewhere__is_traversed",
        given=[
            File(os.path.join("elsewhere", "file")),
            AbsoluteSymlink(os.path.join("here", "symlink"), "elsewhere"),
        ],
        add=[AddCall(path="here")],
        expect=[
            ExpectedTraverseStep("here", subdirs=["symlink"]),
            ExpectedTraverseStep(str(Path("here", "symlink")), files=["file"]),
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
                ExpectedTraverseStep(".", subdirs=["dir", "rel_link", "abs_link"]),
                ExpectedTraverseStep("dir", files=["file"]),
            ],
            [
                ExpectedTraverseStep(".", subdirs=["dir", "rel_link", "abs_link"]),
                ExpectedTraverseStep("rel_link", files=["file"]),
            ],
            [
                ExpectedTraverseStep(".", subdirs=["dir", "rel_link", "abs_link"]),
                ExpectedTraverseStep("abs_link", files=["file"]),
            ],
        ],
    ),
]


@pytest.mark.parametrize(
    "vector",
    [
        pytest.param(
            v,
            id=v.id,
            marks=pytest.mark.skipif(
                sys.platform.startswith("win")
                and any(
                    isinstance(entry, (RelativeSymlink, AbsoluteSymlink))
                    for entry in v.given
                ),
                reason="Symlinks on Windows may be created only by administrators",
            ),
        )
        for v in directory_traversal_vectors
    ],
)
def test_DirectoryTraversal(vector: DirectoryTraversalVector, tmp_path):
    for entry in vector.given:
        entry(tmp_path)

    traversal: DirectoryTraversal = DirectoryTraversal()
    for call in vector.add:
        traversal.add(tmp_path / call.path, *call.attach)
    for path in vector.skip_dirs:
        traversal.skip_dir(tmp_path / path)

    actual = list(traversal.traverse())
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
