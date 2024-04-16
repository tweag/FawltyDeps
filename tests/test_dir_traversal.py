"""Test core functionality of DirectoryTraversal class."""

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent
from typing import Generic, List, Optional, Tuple, Type, TypeVar, Union

import pytest

from fawltydeps.dir_traversal import DirectoryTraversal, TraversalStep
from fawltydeps.gitignore_parser import RuleError, RuleMissing

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
        path = tmp_path / self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(tmp_path.resolve() / self.target)


@dataclass
class ExpectedTraverseStep(Generic[T]):
    """Expected data for one step of DirectoryTraversal."""

    # All strings are relative to tmp_path
    dir: str
    subdirs: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    attached: List[T] = field(default_factory=list)
    excluded_subdirs: List[str] = field(default_factory=list)
    excluded_files: List[str] = field(default_factory=list)

    def prepare(self, tmp_path: Path) -> TraversalStep:
        return TraversalStep(
            tmp_path / self.dir,
            frozenset(tmp_path / self.dir / d for d in self.subdirs),
            frozenset(tmp_path / self.dir / f for f in self.files),
            self.attached,
            frozenset(tmp_path / self.dir / d for d in self.excluded_subdirs),
            frozenset(tmp_path / self.dir / f for f in self.excluded_files),
        )


@dataclass(frozen=True)
class AddCall(Generic[T]):
    """Arguments for a call to DirectoryTraversal.add()."""

    path: Union[Path, str]
    attach: Tuple[T, ...] = ()


@dataclass(frozen=True)
class ExcludePattern:
    """Arguments for a call to DirectoryTraversal.exclude()."""

    pattern: str
    # DirectoryTraversal.exclude() defaults to base_dir=None.
    # Here, instead, we default base_dir to "" (which is automatically prefixed
    # by tmp_path in the test code below). This makes it easier to test anchored
    # exclude patterns. Pass None explicitly to test the default .exclude()
    # behavior (which will cause anchored patterns to raise RuleError).
    base_dir: Optional[str] = ""


@dataclass(frozen=True)
class DirectoryTraversalVector:
    """Test vectors for DirectoryTraversal."""

    id: str
    given: List[BaseEntry]
    add: List[AddCall] = field(default_factory=lambda: [AddCall(path=".")])
    skip_dirs: List[str] = field(default_factory=list)
    exclude_patterns: List[ExcludePattern] = field(default_factory=list)
    exclude_from: List[str] = field(default_factory=list)
    exclude_exceptions: List[Type[Exception]] = field(default_factory=list)
    expect: List[ExpectedTraverseStep] = field(default_factory=list)
    expect_alternatives: Optional[List[List[ExpectedTraverseStep]]] = None
    skip_me: Optional[str] = None

    def setup(self, setup_dir: Path) -> DirectoryTraversal:  # noqa: C901
        """Perform the setup of a DirectoryTraversal object.

        Set up the file structure in self.given under the given 'setup_dir', and
        prepare a new DirectoryTraversal object by calling .add(), .skip_dir(),
        and .exclude() as indicated by the corresponding members of self.
        Also verify any exceptions raised by .exclude() against
        self.exclude_exceptions.

        Return the DirectoryTraversal object without calling .traverse() on it.
        """
        if self.skip_me is not None:
            pytest.skip(self.skip_me)

        for entry in self.given:
            entry(setup_dir)

        traversal: DirectoryTraversal = DirectoryTraversal()
        for call in self.add:
            traversal.add(setup_dir / call.path, *call.attach)
        for path in self.skip_dirs:
            traversal.skip_dir(setup_dir / path)
        exceptions_from_exclude = []
        for ipat in self.exclude_patterns:
            base_dir = None if ipat.base_dir is None else setup_dir / ipat.base_dir
            try:
                traversal.exclude(ipat.pattern, base_dir=base_dir)
            except Exception as e:  # noqa: BLE001
                exceptions_from_exclude.append(e)
        for exclude_file in self.exclude_from:
            try:
                traversal.exclude_from(setup_dir / exclude_file)
            except Exception as e:  # noqa: BLE001
                exceptions_from_exclude.append(e)
        if not self.exclude_exceptions:  # no exceptions are expected
            for exc in exceptions_from_exclude:
                raise exc  # raise the exception itself here
        assert self.exclude_exceptions == [type(e) for e in exceptions_from_exclude]

        return traversal

    def verify_traversal(self, traversal: DirectoryTraversal, setup_dir: Path) -> None:
        """Perform the traversal and verify that expectations hold."""
        actual = list(traversal.traverse())
        if self.expect_alternatives is None:  # self.expect _must_ match
            expect = [step.prepare(setup_dir) for step in self.expect]
            assert_unordered_equivalence(actual, expect)
        else:  # one of the alternatives must match
            for alternative in self.expect_alternatives:
                expect = [step.prepare(setup_dir) for step in alternative]
                try:
                    assert_unordered_equivalence(actual, expect)
                except AssertionError:  # this alternative failed
                    continue  # skip to next alternative
                else:  # this alternative passed
                    break  # abort loop and skip below else clause
            else:  # we exhausted all alternatives
                pytest.fail(f"None of the alternatives matched {actual}")


def on_windows(msg: str) -> Optional[str]:
    """Helper used by .skip_me to skip certain tests on Windows."""
    return msg if sys.platform.startswith("win") else None


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
        skip_me=on_windows("Symlinks on Windows may be created only by administrators"),
    ),
    DirectoryTraversalVector(
        "symlinks_to_parent__are_not_traversed",
        given=[
            RelativeSymlink(str(Path("sub", "rel_parent")), ".."),
            AbsoluteSymlink(str(Path("sub", "abs_parent")), "."),
        ],
        expect=[
            ExpectedTraverseStep(".", subdirs=["sub"]),
            ExpectedTraverseStep("sub", subdirs=["rel_parent", "abs_parent"]),
        ],
        skip_me=on_windows("Symlinks on Windows may be created only by administrators"),
    ),
    DirectoryTraversalVector(
        "mutual_symlinks__are_traversed_once",
        given=[
            RelativeSymlink(
                str(Path("sub1", "rel_link_sub2")), str(Path("..", "sub2"))
            ),
            AbsoluteSymlink(str(Path("sub2", "abs_link_sub1")), "sub1"),
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
        skip_me=on_windows("Symlinks on Windows may be created only by administrators"),
    ),
    DirectoryTraversalVector(
        "relative_symlink_to_dir_elsewhere__is_traversed",
        given=[
            File(str(Path("elsewhere", "file"))),
            RelativeSymlink(str(Path("here", "symlink")), str(Path("..", "elsewhere"))),
        ],
        add=[AddCall(path="here")],
        expect=[
            ExpectedTraverseStep("here", subdirs=["symlink"]),
            ExpectedTraverseStep(str(Path("here", "symlink")), files=["file"]),
        ],
        skip_me=on_windows("Symlinks on Windows may be created only by administrators"),
    ),
    DirectoryTraversalVector(
        "absolute_symlink_to_dir_elsewhere__is_traversed",
        given=[
            File(str(Path("elsewhere", "file"))),
            AbsoluteSymlink(str(Path("here", "symlink")), "elsewhere"),
        ],
        add=[AddCall(path="here")],
        expect=[
            ExpectedTraverseStep("here", subdirs=["symlink"]),
            ExpectedTraverseStep(str(Path("here", "symlink")), files=["file"]),
        ],
        skip_me=on_windows("Symlinks on Windows may be created only by administrators"),
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
        skip_me=on_windows("Symlinks on Windows may be created only by administrators"),
    ),
    DirectoryTraversalVector(
        "excluded_dot_dirs__are_not_traversed",
        given=[
            File(".venv/sub/file"),
            File("dir/.venv/sub/file"),
            File("dir/foo.py"),
        ],
        exclude_patterns=[ExcludePattern(".*")],  # exclude paths that start with "."
        expect=[
            ExpectedTraverseStep(".", subdirs=["dir"], excluded_subdirs=[".venv"]),
            ExpectedTraverseStep("dir", files=["foo.py"], excluded_subdirs=[".venv"]),
        ],
    ),
    DirectoryTraversalVector(
        "excluded_dot_dirs__are_traversed_if_they_are_also_explicitly_added",
        given=[
            File(".venv/sub/file"),
            File("dir/.venv/sub/file"),
            File("dir/foo.py"),
        ],
        add=[AddCall(path=".", attach=(123,)), AddCall(path=".venv", attach=(456,))],
        exclude_patterns=[ExcludePattern(".*")],  # exclude paths that start with "."
        expect=[
            ExpectedTraverseStep(".", subdirs=[".venv", "dir"], attached=[123]),
            ExpectedTraverseStep(".venv", subdirs=["sub"], attached=[123, 456]),
            ExpectedTraverseStep(".venv/sub", files=["file"], attached=[123, 456]),
            ExpectedTraverseStep(
                "dir", files=["foo.py"], excluded_subdirs=[".venv"], attached=[123]
            ),
        ],
    ),
    #
    # Testing exclude patterns stand-alone
    #
    # The following tests are based on the pattern format rules listed in
    # `git help ignore` (https://git-scm.com/docs/gitignore#_pattern_format).
    #
    # A blank line matches no files, so it can serve as a separator for
    # readability.
    DirectoryTraversalVector(
        "gitignore_parsing__disregard_blank_lines",
        given=[File("dir/file")],
        exclude_patterns=[ExcludePattern(""), ExcludePattern("")],
        exclude_exceptions=[RuleMissing, RuleMissing],
        expect=[
            ExpectedTraverseStep(".", subdirs=["dir"]),
            ExpectedTraverseStep("dir", files=["file"]),
        ],
    ),
    # A line starting with # serves as a comment. Put a backslash ("\") in
    # front of the first hash for patterns that begin with a hash.
    DirectoryTraversalVector(
        "gitignore_parsing__disregard_comments",
        given=[
            File("#do_not_exclude"),
            File("#do_exclude"),
        ],
        exclude_patterns=[
            ExcludePattern("#do_not_exclude"),  # comment
            ExcludePattern("\\#do_exclude"),  # match literal '#'
        ],
        exclude_exceptions=[RuleMissing],
        expect=[
            ExpectedTraverseStep(
                ".", files=["#do_not_exclude"], excluded_files=["#do_exclude"]
            ),
        ],
    ),
    # Trailing spaces are excluded unless they are quoted with backslash ("\").
    DirectoryTraversalVector(
        "gitignore_parsing__disregard_trailing_spaces",
        given=[
            File("do_not_exclude "),
            File("do_exclude "),
        ],
        exclude_patterns=[
            ExcludePattern("do_not_exclude "),  # disregard this trailing space
            ExcludePattern("do_exclude\\ "),  # match literal trailing space
        ],
        expect=[
            ExpectedTraverseStep(
                ".", files=["do_not_exclude "], excluded_files=["do_exclude "]
            ),
        ],
        skip_me=on_windows("Windows does not support paths with trailing spaces"),
        # https://stackoverflow.com/a/67886889
    ),
    # An optional prefix "!" which negates the pattern; any matching file
    # excluded by a previous pattern will become included again. It is not
    # possible to re-include a file if a parent directory of that file is
    # excluded. Git doesn't list excluded directories for performance reasons,
    # so any patterns on contained files have no effect, no matter where they
    # are defined. Put a backslash ("\") in front of the first "!" for patterns
    # that begin with a literal "!", for example, "\!important!.txt".
    DirectoryTraversalVector(
        "gitignore_parsing__negated_patterns_override_earlier_exclude",
        given=[
            File("do_not_exclude"),
            File("do_exclude"),
        ],
        exclude_patterns=[
            ExcludePattern("*exclude"),
            ExcludePattern("!do_not_exclude"),
        ],
        expect=[
            ExpectedTraverseStep(
                ".", files=["do_not_exclude"], excluded_files=["do_exclude"]
            ),
        ],
    ),
    DirectoryTraversalVector(
        "gitignore_parsing__cannot_negate_if_parent_dir_is_already_excluded",
        given=[
            File("do_exclude/do_not_exclude"),
            File("do_not_exclude"),
        ],
        exclude_patterns=[
            ExcludePattern("do_exclude"),  # excludes directory
            ExcludePattern("!do_not_exclude"),  # ineffective inside excluded dir
        ],
        expect=[
            ExpectedTraverseStep(
                ".", files=["do_not_exclude"], excluded_subdirs=["do_exclude"]
            ),
        ],
    ),
    DirectoryTraversalVector(
        "gitignore_parsing__escape_literal_exclamation_mark",
        given=[
            File("!exclude_me!"),
            File("exclude_me!"),
        ],
        exclude_patterns=[ExcludePattern("\\!exclude_me!")],  # matches 1st entry above
        expect=[
            ExpectedTraverseStep(
                ".", files=["exclude_me!"], excluded_files=["!exclude_me!"]
            ),
        ],
    ),
    # The slash "/" is used as the directory separator. Separators may occur at
    # the beginning, middle or end of the .gitignore search pattern.
    #
    # If there is a separator at the beginning or middle (or both) of the
    # pattern, then the pattern is relative to the directory level of the
    # particular .gitignore file itself. Otherwise the pattern may also match
    # at any level below the .gitignore level.
    DirectoryTraversalVector(
        "exclude_pattern_with_slash_at_beginning__anchors_to_current_dir",
        given=[
            File("a/file"),
            File("file"),
        ],
        exclude_patterns=[ExcludePattern("/file")],  # matches 2nd, but not 1st
        expect=[
            ExpectedTraverseStep(".", subdirs=["a"], excluded_files=["file"]),
            ExpectedTraverseStep("a", files=["file"]),
        ],
    ),
    DirectoryTraversalVector(
        "anchored_pattern__must_have_base_dir",
        given=[File("file")],
        exclude_patterns=[ExcludePattern("/file", None)],
        exclude_exceptions=[RuleError],
        expect=[ExpectedTraverseStep(".", files=["file"])],
    ),
    DirectoryTraversalVector(
        "exclude_pattern_with_slash_in_middle__anchors_to_current_dir",
        given=[
            File("a/b/file"),
            File("b/file"),
        ],
        exclude_patterns=[ExcludePattern("b/file")],  # matches 2nd, but not 1st
        expect=[
            ExpectedTraverseStep(".", subdirs=["a", "b"]),
            ExpectedTraverseStep("a", subdirs=["b"]),
            ExpectedTraverseStep("a/b", files=["file"]),
            ExpectedTraverseStep("b", excluded_files=["file"]),
        ],
    ),
    DirectoryTraversalVector(
        "exclude_pattern_without_slash__matches_at_any_level",
        given=[
            File("a/b/file"),
            File("b/file"),
            File("file"),
        ],
        exclude_patterns=[ExcludePattern("file")],  # matches all
        expect=[
            ExpectedTraverseStep(".", subdirs=["a", "b"], excluded_files=["file"]),
            ExpectedTraverseStep("a", subdirs=["b"]),
            ExpectedTraverseStep("a/b", excluded_files=["file"]),
            ExpectedTraverseStep("b", excluded_files=["file"]),
        ],
    ),
    DirectoryTraversalVector(
        "exclude_pattern_without_slash__does_not_match_above_base_dir",
        given=[
            File("file"),
            File("a/file"),
            File("a/b/file"),
        ],
        exclude_patterns=[ExcludePattern("file", "a/")],
        expect=[
            ExpectedTraverseStep(".", subdirs=["a"], files=["file"]),
            ExpectedTraverseStep("a", subdirs=["b"], excluded_files=["file"]),
            ExpectedTraverseStep("a/b", excluded_files=["file"]),
        ],
    ),
    # If there is a separator at the end of the pattern then the pattern will
    # only match directories, otherwise the pattern can match both files and
    # directories.
    DirectoryTraversalVector(
        "exclude_pattern_with_slash_at_end__matches_dirs_only",
        given=[
            File("dir1/some_path"),  # some_path is not a dir
            File("dir2/some_path/a_file"),  # some_path is a dir
        ],
        exclude_patterns=[ExcludePattern("some_path/")],  # matches 2nd, but not 1st
        expect=[
            ExpectedTraverseStep(".", subdirs=["dir1", "dir2"]),
            ExpectedTraverseStep("dir1", files=["some_path"]),
            ExpectedTraverseStep("dir2", excluded_subdirs=["some_path"]),
        ],
    ),
    DirectoryTraversalVector(
        "exclude_pattern_without_slash_at_end__matches_dir_and_file",
        given=[
            File("dir1/some_path"),  # some_path is not a dir
            File("dir2/some_path/a_file"),  # some_path is a dir
        ],
        exclude_patterns=[ExcludePattern("some_path")],  # matches both
        expect=[
            ExpectedTraverseStep(".", subdirs=["dir1", "dir2"]),
            ExpectedTraverseStep("dir1", excluded_files=["some_path"]),
            ExpectedTraverseStep("dir2", excluded_subdirs=["some_path"]),
        ],
    ),
    DirectoryTraversalVector(
        "exclude_pattern_with_slash_at_end__overridden_by_specified_path",
        given=[File("dir/some_path/a_file")],
        exclude_patterns=[ExcludePattern("some_path/")],
        add=[AddCall(path="."), AddCall(path="dir/some_path")],
        expect=[
            ExpectedTraverseStep(".", subdirs=["dir"]),
            ExpectedTraverseStep("dir", subdirs=["some_path"]),
            ExpectedTraverseStep("dir/some_path", files=["a_file"]),
        ],
    ),
    DirectoryTraversalVector(
        "exclude_pattern_without_slash_at_end__overridden_by_specified_path",
        given=[File("dir/some_path/a_file")],
        exclude_patterns=[ExcludePattern("some_path")],
        add=[AddCall(path="."), AddCall(path="dir/some_path")],
        expect=[
            ExpectedTraverseStep(".", subdirs=["dir"]),
            ExpectedTraverseStep("dir", subdirs=["some_path"]),
            ExpectedTraverseStep("dir/some_path", files=["a_file"]),
        ],
    ),
    DirectoryTraversalVector(
        "exclude_pattern_with_combined_slashes_and_base_dir",
        given=[
            Dir("b"),
            Dir("a/b"),
            Dir("a/a/b"),  # below pattern matches only this
            Dir("a/a/a/b"),
        ],
        exclude_patterns=[ExcludePattern("a/b/", "a/")],
        expect=[
            ExpectedTraverseStep(".", subdirs=["a", "b"]),
            ExpectedTraverseStep("a", subdirs=["a", "b"]),
            ExpectedTraverseStep("a/a", subdirs=["a"], excluded_subdirs=["b"]),
            ExpectedTraverseStep("a/a/a", subdirs=["b"]),
            ExpectedTraverseStep("a/a/a/b"),
            ExpectedTraverseStep("a/b"),
            ExpectedTraverseStep("b"),
        ],
    ),
    # For example, a pattern doc/frotz/ matches doc/frotz directory, but not
    # a/doc/frotz directory; however frotz/ matches frotz and a/frotz that is
    # a directory (all paths are relative from the .gitignore file).
    DirectoryTraversalVector(
        "exclude_pattern__doc_frotz_example",
        given=[
            Dir("doc/frotz"),
            Dir("a/doc/frotz"),
        ],
        exclude_patterns=[ExcludePattern("doc/frotz/")],  # matches 1st, but not 2nd
        expect=[
            ExpectedTraverseStep(".", subdirs=["a", "doc"]),
            ExpectedTraverseStep("a", subdirs=["doc"]),
            ExpectedTraverseStep("a/doc", subdirs=["frotz"]),
            ExpectedTraverseStep("a/doc/frotz"),
            ExpectedTraverseStep("doc", excluded_subdirs=["frotz"]),
        ],
    ),
    DirectoryTraversalVector(
        "exclude_pattern__frotz_example",
        given=[
            Dir("frotz"),
            Dir("a/frotz"),
        ],
        exclude_patterns=[ExcludePattern("frotz/")],  # matches both
        expect=[
            ExpectedTraverseStep(".", subdirs=["a"], excluded_subdirs=["frotz"]),
            ExpectedTraverseStep("a", excluded_subdirs=["frotz"]),
        ],
    ),
    # An asterisk "*" matches anything except a slash. The character "?" matches
    # any one character except "/". The range notation, e.g. [a-zA-Z], can be
    # used to match one of the characters in a range. See fnmatch(3) and the
    # FNM_PATHNAME flag for a more detailed description.
    DirectoryTraversalVector(
        "asterisk_matches_anything_except_slash",
        given=[
            File("abcdef"),
            File("abcxyzdef"),
            File("abcdefdef"),
            File("abcabcdef"),
            File("abc/def"),  # not matched
        ],
        exclude_patterns=[ExcludePattern("abc*def")],
        expect=[
            ExpectedTraverseStep(
                ".",
                subdirs=["abc"],
                excluded_files=["abcdef", "abcxyzdef", "abcdefdef", "abcabcdef"],
            ),
            ExpectedTraverseStep("abc", files=["def"]),
        ],
    ),
    DirectoryTraversalVector(
        "question_mark_matches_any_one_char_except_slash",
        given=[
            File("abcdef"),  # not matched
            File("abcxdef"),
            File("abcddef"),
            File("abc/def"),  # not matched
        ],
        exclude_patterns=[ExcludePattern("abc?def")],
        expect=[
            ExpectedTraverseStep(
                ".",
                subdirs=["abc"],
                files=["abcdef"],
                excluded_files=["abcxdef", "abcddef"],
            ),
            ExpectedTraverseStep("abc", files=["def"]),
        ],
    ),
    DirectoryTraversalVector(
        "range_matches_any_one_char_in_range",
        given=[
            File("abcdef"),  # not matched
            File("abcWdef"),  # not matched
            File("abcXdef"),
            File("abcYdef"),
            File("abcZdef"),
            File("abcXYXdef"),  # not matched
            File("abc/def"),  # not matched
        ],
        exclude_patterns=[ExcludePattern("abc[X-Z]def")],
        expect=[
            ExpectedTraverseStep(
                ".",
                subdirs=["abc"],
                files=["abcdef", "abcWdef", "abcXYXdef"],
                excluded_files=["abcXdef", "abcYdef", "abcZdef"],
            ),
            ExpectedTraverseStep("abc", files=["def"]),
        ],
    ),
    DirectoryTraversalVector(
        "range_with_slash_does_not_match_dir_separator",
        given=[
            File("abcdef"),  # not matched
            File("abcXdef"),
            File("abc/def"),  # not matched, see FNM_PATHNAME in fnmatch(3)
        ],
        exclude_patterns=[ExcludePattern("abc[X-Z/]def")],
        expect=[
            ExpectedTraverseStep(
                ".", subdirs=["abc"], files=["abcdef"], excluded_files=["abcXdef"]
            ),
            ExpectedTraverseStep("abc", files=["def"]),
        ],
    ),
    # Two consecutive asterisks ("**") in patterns matched against full pathname
    # may have special meaning:
    #
    # A leading "**" followed by a slash means match in all directories.
    # For example, "**/foo" matches file or directory "foo" anywhere, the same
    # as pattern "foo". "**/foo/bar" matches file or directory "bar" anywhere
    # that is directly under directory "foo".
    DirectoryTraversalVector(
        "exclude_pattern_double_asterisk_slash_matches_in_all_dirs_under_base",
        given=[
            File("foo"),  # not matched, due to base_dir a/
            File("a/foo"),
            File("a/b/foo"),
            File("a/c/foo/more"),
        ],
        exclude_patterns=[ExcludePattern("**/foo", "a/")],
        expect=[
            ExpectedTraverseStep(".", subdirs=["a"], files=["foo"]),
            ExpectedTraverseStep("a", subdirs=["b", "c"], excluded_files=["foo"]),
            ExpectedTraverseStep("a/b", excluded_files=["foo"]),
            ExpectedTraverseStep("a/c", excluded_subdirs=["foo"]),
        ],
    ),
    DirectoryTraversalVector(
        "exclude_pattern_double_asterisk_and_multiple_slashes",
        given=[
            File("foo/bar"),  # not matched, due to base_dir a/
            File("a/foo/bar/file"),
            File("a/foo/baz/file"),  # does not match
            File("a/b/foo/bar"),
            File("a/c/bar"),  # does not match
            Dir("a/c/foo/bar"),
        ],
        exclude_patterns=[ExcludePattern("**/foo/bar", "a/")],
        expect=[
            ExpectedTraverseStep(".", subdirs=["a", "foo"]),
            ExpectedTraverseStep("a", subdirs=["foo", "b", "c"]),
            ExpectedTraverseStep("a/foo", subdirs=["baz"], excluded_subdirs=["bar"]),
            ExpectedTraverseStep("a/foo/baz", files=["file"]),
            ExpectedTraverseStep("a/b", subdirs=["foo"]),
            ExpectedTraverseStep("a/b/foo", excluded_files=["bar"]),
            ExpectedTraverseStep("a/c", subdirs=["foo"], files=["bar"]),
            ExpectedTraverseStep("a/c/foo", excluded_subdirs=["bar"]),
            ExpectedTraverseStep("foo", files=["bar"]),
        ],
    ),
    # A trailing "/**" matches everything inside. For example, "abc/**" matches
    # all files inside directory "abc", relative to the location of the
    # .gitignore file, with infinite depth.
    DirectoryTraversalVector(
        "trailing_double_asterisk_after_slash_matches_everything_underneath",
        given=[
            File("abc/def"),
            File("abc/a/very/long/and/deeply/nested/subdir/with/files/in/it"),
            File("abx/yz"),  # not matched
        ],
        exclude_patterns=[ExcludePattern("abc/**")],
        expect=[
            ExpectedTraverseStep(".", subdirs=["abc", "abx"]),
            ExpectedTraverseStep("abc", excluded_subdirs=["a"], excluded_files=["def"]),
            ExpectedTraverseStep("abx", files=["yz"]),
        ],
    ),
    # A slash followed by two consecutive asterisks then a slash matches zero or
    # more directories. For example, "a/**/b" matches "a/b", "a/x/b", "a/x/y/b"
    # and so on.
    DirectoryTraversalVector(
        "double_asterisk_between_slashes_matches_zero_or_more_dir_levels",
        given=[
            File("a/b"),
            File("a/x/b"),
            File("a/x/y/b"),
            File("a/x/z/b/also_excluded"),
            File("a/x/bb"),  # not matched
            File("a/c"),  # not matched
            File("foo/a/b/c"),  # not matched, because a/**/b is anchored
        ],
        exclude_patterns=[ExcludePattern("a/**/b")],
        expect=[
            ExpectedTraverseStep(".", subdirs=["a", "foo"]),
            ExpectedTraverseStep("a", subdirs=["x"], files=["c"], excluded_files=["b"]),
            ExpectedTraverseStep(
                "a/x", subdirs=["y", "z"], files=["bb"], excluded_files=["b"]
            ),
            ExpectedTraverseStep("a/x/y", excluded_files=["b"]),
            ExpectedTraverseStep("a/x/z", excluded_subdirs=["b"]),
            ExpectedTraverseStep("foo", subdirs=["a"]),
            ExpectedTraverseStep("foo/a", subdirs=["b"]),
            ExpectedTraverseStep("foo/a/b", files=["c"]),
        ],
    ),
    # Other consecutive asterisks are considered regular asterisks and will
    # match according to the previous rules.
    DirectoryTraversalVector(
        "double_asterisk_elsewhere_is_equivalent_to_single_asterisk",
        given=[
            File("a/bc/d"),
            File("a/bXc/d/also_excluded"),
            File("a/bbc/d"),
            File("a/bcc/d"),
            File("a/bcd"),  # not matched
            File("a/b/c/d"),  # not matched
            File("a/bb/cc/d"),  # not matched
            File("a/bb/XX/cc/d"),  # not matched
        ],
        exclude_patterns=[ExcludePattern("a/b**c/d")],
        expect=[
            ExpectedTraverseStep(".", subdirs=["a"]),
            ExpectedTraverseStep(
                "a", subdirs=["bc", "bXc", "bbc", "bcc", "b", "bb"], files=["bcd"]
            ),
            ExpectedTraverseStep("a/bc", excluded_files=["d"]),
            ExpectedTraverseStep("a/bXc", excluded_subdirs=["d"]),
            ExpectedTraverseStep("a/bbc", excluded_files=["d"]),
            ExpectedTraverseStep("a/bcc", excluded_files=["d"]),
            ExpectedTraverseStep("a/b", subdirs=["c"]),
            ExpectedTraverseStep("a/b/c", files=["d"]),
            ExpectedTraverseStep("a/bb", subdirs=["cc", "XX"]),
            ExpectedTraverseStep("a/bb/cc", files=["d"]),
            ExpectedTraverseStep("a/bb/XX", subdirs=["cc"]),
            ExpectedTraverseStep("a/bb/XX/cc", files=["d"]),
        ],
    ),
    DirectoryTraversalVector(
        "multi_asterisks_elsewhere_is_equivalent_to_single_asterisk",
        given=[
            File("a/bc/d"),
            File("a/b/c/d"),  # not matched
            File("xfoo"),
            File("x/foo"),  # not matched
            File("barx"),
        ],
        exclude_patterns=[
            ExcludePattern("a/b***c/d"),
            ExcludePattern("/****foo"),
            ExcludePattern("bar***"),
        ],
        expect=[
            ExpectedTraverseStep(
                ".", subdirs=["a", "x"], excluded_files=["xfoo", "barx"]
            ),
            ExpectedTraverseStep("a", subdirs=["bc", "b"]),
            ExpectedTraverseStep("a/bc", excluded_files=["d"]),
            ExpectedTraverseStep("a/b", subdirs=["c"]),
            ExpectedTraverseStep("a/b/c", files=["d"]),
            ExpectedTraverseStep("x", files=["foo"]),
        ],
    ),
    #
    # Testing exclude patterns read from (and interpreted relative to) files.
    #
    DirectoryTraversalVector(
        "gitignore_file__disregard_blank_lines_and_comments",
        given=[
            File(
                ".gitignore",
                dedent(
                    """\
                    # A comment
                        \\

                    \t
                    #another comment
                    exclude_this_file
                    """
                ),
            ),
            File("exclude_this_file"),
        ],
        exclude_from=[".gitignore"],
        expect=[
            ExpectedTraverseStep(
                ".", files=[".gitignore"], excluded_files=["exclude_this_file"]
            ),
        ],
    ),
    DirectoryTraversalVector(
        "gitignore_file__does_not_apply_to_parent_or_sibling_dirs",
        given=[
            File("foo"),
            File("sibling/foo"),
            File("sub/.gitignore", "foo"),  # exclude foo underneath sub/
            File("sub/foo"),  # excluded
            File("sub/bar/foo"),  # also excluded
        ],
        exclude_from=["sub/.gitignore"],
        expect=[
            ExpectedTraverseStep(".", subdirs=["sibling", "sub"], files=["foo"]),
            ExpectedTraverseStep("sibling", files=["foo"]),
            ExpectedTraverseStep(
                "sub", subdirs=["bar"], files=[".gitignore"], excluded_files=["foo"]
            ),
            ExpectedTraverseStep("sub/bar", excluded_files=["foo"]),
        ],
    ),
    DirectoryTraversalVector(
        "gitignore_file__anchored_pattern_only_applies_to_parent_or_sibling_dirs",
        given=[
            File("foo"),
            File("sub/.gitignore", "/foo"),  # exclude foo only in sub/ itself
            File("sub/foo"),  # excluded
            File("sub/bar/foo"),
        ],
        exclude_from=["sub/.gitignore"],
        expect=[
            ExpectedTraverseStep(".", subdirs=["sub"], files=["foo"]),
            ExpectedTraverseStep(
                "sub", subdirs=["bar"], files=[".gitignore"], excluded_files=["foo"]
            ),
            ExpectedTraverseStep("sub/bar", files=["foo"]),
        ],
    ),
    DirectoryTraversalVector(
        "gitignore_file__cannot_exclude_files_in_parent_dir",
        given=[
            File("foo"),
            File("bar"),
            File("sub/.gitignore", "../bar"),  # try (and fail) to exclude ../bar
        ],
        exclude_from=["sub/.gitignore"],
        expect=[
            ExpectedTraverseStep(".", subdirs=["sub"], files=["foo", "bar"]),
            ExpectedTraverseStep("sub", files=[".gitignore"]),
        ],
    ),
    DirectoryTraversalVector(
        "gitignore_file__can_be_used_to_exclude_this_dir",
        given=[
            File("foo"),
            File("sub/.gitignore", "."),  # exclude all of sub/
            File("sub/foo"),  # excluded
        ],
        exclude_from=["sub/.gitignore"],
        expect=[
            ExpectedTraverseStep(".", files=["foo"], excluded_subdirs=["sub"]),
        ],
    ),
    DirectoryTraversalVector(
        "gitignore_file__parse_multiple_gitignores__and_use_patterns_from_all",
        given=[
            File(".gitignore", "foo"),  # exclude foo in ./ and ./sub/
            File("foo"),
            File("bar"),
            File("sub/.gitignore", "bar"),  # exclude bar in sub/ only
            File("sub/foo"),
            File("sub/bar"),
        ],
        exclude_from=[".gitignore", "sub/.gitignore"],
        expect=[
            ExpectedTraverseStep(
                ".",
                subdirs=["sub"],
                files=[".gitignore", "bar"],
                excluded_files=["foo"],
            ),
            ExpectedTraverseStep(
                "sub", files=[".gitignore"], excluded_files=["foo", "bar"]
            ),
        ],
    ),
    #
    # Testing combination of .exclude() and .exclude_from() patterns
    #
    DirectoryTraversalVector(
        "exclude_patterns_take_precedence_over_exclude_from_patterns",
        given=[
            File(".gitignore", "foo/*"),  # exclude everything inside foo/
            File("foo/bar"),  # NOT excluded due to exclude_pattern below
            File("foo/baz"),  # excluded
        ],
        exclude_patterns=[
            ExcludePattern("!foo/bar"),  # overrides "foo/*" in .gitignore
        ],
        exclude_from=[".gitignore"],
        expect=[
            ExpectedTraverseStep(".", subdirs=["foo"], files=[".gitignore"]),
            ExpectedTraverseStep("foo", files=["bar"], excluded_files=["baz"]),
        ],
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in directory_traversal_vectors]
)
def test_DirectoryTraversal_w_abs_paths(vector: DirectoryTraversalVector, tmp_path):
    traversal = vector.setup(tmp_path)  # Traverse tmp_path with absolute paths
    vector.verify_traversal(traversal, tmp_path)


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in directory_traversal_vectors]
)
def test_DirectoryTraversal_w_rel_paths(
    vector: DirectoryTraversalVector,
    inside_tmp_path,  # noqa: ARG001
):
    traversal = vector.setup(Path())  # Traverse relatively from inside tmp_path
    vector.verify_traversal(traversal, Path())


def test_DirectoryTraversal__raises_error__when_adding_missing_dir(tmp_path):
    traversal = DirectoryTraversal()
    with pytest.raises(NotADirectoryError):
        traversal.add(tmp_path / "MISSING")
