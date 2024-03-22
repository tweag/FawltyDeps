"""Verify behavior of gitignore_parser."""

import sys
from pathlib import Path
from typing import List, NamedTuple, Union

import pytest

from fawltydeps.gitignore_parser import match_rules, parse_gitignore_lines

PathOrStr = Union[str, Path]


class GitignoreParserTestVector(NamedTuple):
    """Test patterns expected matches/non-matches."""

    id: str
    patterns: List[str]
    does_match: List[PathOrStr]
    doesnt_match: List[PathOrStr]
    base_dir: str = "."


test_vectors = [
    GitignoreParserTestVector(
        "simple",
        ["__pycache__/", "*.py[cod]"],
        does_match=["main.pyc", "dir/main.pyc", "__pycache__/"],
        doesnt_match=["main.py"],
    ),
    GitignoreParserTestVector(
        "incomplete_filename",
        ["o.py"],
        does_match=["o.py", "dir/o.py"],
        doesnt_match=["foo.py", "o.pyc", "dir/foo.py", "dir/o.pyc"],
    ),
    GitignoreParserTestVector(
        "wildcard",
        ["hello.*"],
        does_match=["hello.txt", "hello.foobar/", "dir/hello.txt", "hello."],
        doesnt_match=["hello", "helloX"],
    ),
    GitignoreParserTestVector(
        "anchored_wildcard",
        ["/hello.*"],
        does_match=["hello.txt", "hello.c"],
        doesnt_match=["a/hello.java"],
    ),
    GitignoreParserTestVector(
        "trailing_spaces",
        [
            "ignoretrailingspace ",
            "notignoredspace\\ ",
            "partiallyignoredspace\\  ",
            "partiallyignoredspace2 \\  ",
            "notignoredmultiplespace\\ \\ \\ ",
        ],
        does_match=[
            "ignoretrailingspace",
            "partiallyignoredspace ",
            "partiallyignoredspace2  ",
            "notignoredspace ",
            "notignoredmultiplespace   ",
        ],
        doesnt_match=[
            "ignoretrailingspace ",
            "partiallyignoredspace  ",
            "partiallyignoredspace",
            "partiallyignoredspace2   ",
            "partiallyignoredspace2 ",
            "partiallyignoredspace2",
            "notignoredspace",
            "notignoredmultiplespace",
        ],
    ),
    GitignoreParserTestVector(
        "comment",
        ["somematch", "#realcomment", "othermatch", "\\#imnocomment"],
        does_match=["somematch", "othermatch", "#imnocomment"],
        doesnt_match=["#realcomment"],
    ),
    GitignoreParserTestVector(
        "ignore_directory",
        [".venv/"],
        does_match=[
            ".venv/",  # a dir
            "subdir/.venv/",
        ],
        doesnt_match=[
            ".venv",  # not a dir
            ".venv_other_folder",
            ".venv_no_folder.py",
            # The following two has been moved from does_match to doesnt_match,
            # and reflect that gitignore_parser no longer evaluates patterns in
            # complete isolation. Instead, it expects parent dirs to be tested/
            # matched _before_ their children. If a parent matches (i.e. should
            # be ignored) then we don't expect the child to be tested at all
            # (i.e. the parent dir is never traversed). Thus, the child is NOT
            # responsible for matching its parent dir against the pattern.
            ".venv/folder/",  # folder/ does not match .venv/
            ".venv/file.txt",  # file.txt does not match .venv/
        ],
    ),
    GitignoreParserTestVector(
        "ignore_directory_also_without_trailing_slash",
        [".venv"],
        does_match=[
            ".venv/",  # a dir
            ".venv",  # not a dir
        ],
        doesnt_match=[
            ".venv_other_folder/",
            ".venv_no_folder.py",
        ],
    ),
    GitignoreParserTestVector(
        "ignore_directory_asterisk",
        [".venv/*"],
        does_match=[".venv/folder/", ".venv/file.txt"],
        doesnt_match=[".venv"],
    ),
    GitignoreParserTestVector(
        "negation",
        ["*.ignore", "!keep.ignore"],
        does_match=["trash.ignore", "waste.ignore"],
        doesnt_match=["keep.ignore"],
    ),
    GitignoreParserTestVector(
        "literal_exclamation_mark",
        ["\\!ignore_me!"],
        does_match=["!ignore_me!"],
        doesnt_match=["ignore_me!", "ignore_me"],
    ),
    GitignoreParserTestVector(
        "double_asterisks",
        ["foo/**/Bar"],
        does_match=["foo/hello/Bar", "foo/world/Bar", "foo/Bar"],
        doesnt_match=["foo/BarBar"],
    ),
    GitignoreParserTestVector(
        "double_asterisk_without_slashes_handled_like_single_asterisk",
        ["a/b**c/d"],
        does_match=["a/bc/d", "a/bXc/d", "a/bbc/d", "a/bcc/d"],
        doesnt_match=["a/bcd", "a/b/c/d", "a/bb/cc/d", "a/bb/XX/cc/d"],
    ),
    GitignoreParserTestVector(
        "more_asterisks_handled_like_single_asterisk_1",
        ["***a/b"],
        does_match=["XYZa/b"],
        doesnt_match=["foo/a/b"],
    ),
    GitignoreParserTestVector(
        "more_asterisks_handled_like_single_asterisk_2",
        ["a/b***"],
        does_match=["a/bXYZ"],
        doesnt_match=["a/b/foo"],
    ),
    GitignoreParserTestVector(
        "directory_only_negation",
        ["data/**", "!data/**/", "!.gitkeep", "!data/01_raw/*"],
        does_match=["data/02_processed/processed_file.csv"],
        doesnt_match=[
            "data/01_raw/",
            "data/01_raw/.gitkeep",
            "data/01_raw/raw_file.csv",
            "data/02_processed/",
            "data/02_processed/.gitkeep",
        ],
    ),
    GitignoreParserTestVector(
        "single_asterisk",
        ["*"],
        does_match=["file.txt", "directory/", "directory-trailing/"],
        doesnt_match=[],
    ),
    GitignoreParserTestVector(
        "supports_path_type_argument",
        ["file1", "!file2"],
        does_match=[Path("file1")],
        doesnt_match=[Path("file2")],
    ),
    GitignoreParserTestVector(
        "slash_in_range_does_not_match_dirs",
        ["abc[X-Z/]def"],
        does_match=["abcXdef", "abcYdef", "abcZdef"],
        doesnt_match=["abcdef", "abc/def", "abcXYZdef"],
    ),
]


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_gitignore_parser_w_abs_paths(vector: GitignoreParserTestVector):
    def absolutify(path: PathOrStr) -> Path:
        """Make relative paths absolute. on both POSIX and Windows."""
        if sys.platform.startswith("win"):
            return Path("C:/some/dir", str(path))
        return Path("/some/dir", path)

    base_dir = absolutify(vector.base_dir)
    rules = list(
        parse_gitignore_lines(vector.patterns, base_dir, base_dir / ".gitignore")
    )
    # Use a trailing '/' in the test vectors to signal is_dir=True.
    # This trailing slash is stripped by Path() in any case.
    for path in vector.does_match:
        assert match_rules(
            rules, absolutify(path), is_dir=isinstance(path, str) and path.endswith("/")
        )
    for path in vector.doesnt_match:
        assert not match_rules(
            rules, absolutify(path), is_dir=isinstance(path, str) and path.endswith("/")
        )


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_gitignore_parser_w_rel_paths(vector: GitignoreParserTestVector):
    rules = list(
        parse_gitignore_lines(
            vector.patterns, Path(vector.base_dir), Path(vector.base_dir, ".gitignore")
        )
    )
    # Use a trailing '/' in the test vectors to signal is_dir=True.
    # This trailing slash is stripped by Path() in any case.
    for path in vector.does_match:
        assert match_rules(
            rules, Path(path), is_dir=isinstance(path, str) and path.endswith("/")
        )
    for path in vector.doesnt_match:
        assert not match_rules(
            rules, Path(path), is_dir=isinstance(path, str) and path.endswith("/")
        )


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="Symlinks on Windows may be created only by administrators",
)
def test_symlink_to_another_directory(tmp_path):
    project_dir = tmp_path / "project_dir"
    link = project_dir / "link"
    target = tmp_path / "another_dir/target"

    project_dir.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)

    rules = list(
        parse_gitignore_lines(["link"], project_dir, project_dir / ".gitignore")
    )
    # Verify behavior according to https://git-scm.com/docs/gitignore#_notes:
    # Symlinks are not followed and are matched as if they were regular files.
    assert match_rules(rules, link, is_dir=False)
