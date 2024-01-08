"""Verify behavior of gitignore_parser."""

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
    base_dir: str = "/some/dir"


test_vectors = [
    GitignoreParserTestVector(
        "simple",
        ["__pycache__/", "*.py[cod]"],
        does_match=[
            "/some/dir/main.pyc",
            "/some/dir/dir/main.pyc",
            "/some/dir/__pycache__/",
        ],
        doesnt_match=["/some/dir/main.py"],
    ),
    GitignoreParserTestVector(
        "incomplete_filename",
        ["o.py"],
        does_match=[
            "/some/dir/o.py",
            "/some/dir/dir/o.py",
        ],
        doesnt_match=[
            "/some/dir/foo.py",
            "/some/dir/o.pyc",
            "/some/dir/dir/foo.py",
            "/some/dir/dir/o.pyc",
        ],
    ),
    GitignoreParserTestVector(
        "wildcard",
        ["hello.*"],
        does_match=[
            "/some/dir/hello.txt",
            "/some/dir/hello.foobar/",
            "/some/dir/dir/hello.txt",
            "/some/dir/hello.",
        ],
        doesnt_match=[
            "/some/dir/hello",
            "/some/dir/helloX",
        ],
    ),
    GitignoreParserTestVector(
        "anchored_wildcard",
        ["/hello.*"],
        does_match=["/some/dir/hello.txt", "/some/dir/hello.c"],
        doesnt_match=["/some/dir/a/hello.java"],
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
            "/some/dir/ignoretrailingspace",
            "/some/dir/partiallyignoredspace ",
            "/some/dir/partiallyignoredspace2  ",
            "/some/dir/notignoredspace ",
            "/some/dir/notignoredmultiplespace   ",
        ],
        doesnt_match=[
            "/some/dir/ignoretrailingspace ",
            "/some/dir/partiallyignoredspace  ",
            "/some/dir/partiallyignoredspace",
            "/some/dir/partiallyignoredspace2   ",
            "/some/dir/partiallyignoredspace2 ",
            "/some/dir/partiallyignoredspace2",
            "/some/dir/notignoredspace",
            "/some/dir/notignoredmultiplespace",
        ],
    ),
    GitignoreParserTestVector(
        "comment",
        ["somematch", "#realcomment", "othermatch", "\\#imnocomment"],
        does_match=[
            "/some/dir/somematch",
            "/some/dir/othermatch",
            "/some/dir/#imnocomment",
        ],
        doesnt_match=["/some/dir/#realcomment"],
    ),
    GitignoreParserTestVector(
        "ignore_directory",
        [".venv/"],
        does_match=[
            "/some/dir/.venv/",  # a dir
            "/some/dir/.venv/folder/",
            "/some/dir/.venv/file.txt",
        ],
        doesnt_match=[
            "/some/dir/.venv",  # not a dir
            "/some/dir/.venv_other_folder",
            "/some/dir/.venv_no_folder.py",
        ],
    ),
    GitignoreParserTestVector(
        "ignore_directory_asterisk",
        [".venv/*"],
        does_match=["/some/dir/.venv/folder/", "/some/dir/.venv/file.txt"],
        doesnt_match=["/some/dir/.venv"],
    ),
    GitignoreParserTestVector(
        "negation",
        ["*.ignore", "!keep.ignore"],
        does_match=["/some/dir/trash.ignore", "/some/dir/waste.ignore"],
        doesnt_match=["/some/dir/keep.ignore"],
    ),
    GitignoreParserTestVector(
        "literal_exclamation_mark",
        ["\\!ignore_me!"],
        does_match=["/some/dir/!ignore_me!"],
        doesnt_match=["/some/dir/ignore_me!", "/some/dir/ignore_me"],
    ),
    GitignoreParserTestVector(
        "double_asterisks",
        ["foo/**/Bar"],
        does_match=[
            "/some/dir/foo/hello/Bar",
            "/some/dir/foo/world/Bar",
            "/some/dir/foo/Bar",
        ],
        doesnt_match=["/some/dir/foo/BarBar"],
    ),
    GitignoreParserTestVector(
        "double_asterisk_without_slashes_handled_like_single_asterisk",
        ["a/b**c/d"],
        does_match=[
            "/some/dir/a/bc/d",
            "/some/dir/a/bXc/d",
            "/some/dir/a/bbc/d",
            "/some/dir/a/bcc/d",
        ],
        doesnt_match=[
            "/some/dir/a/bcd",
            "/some/dir/a/b/c/d",
            "/some/dir/a/bb/cc/d",
            "/some/dir/a/bb/XX/cc/d",
        ],
    ),
    GitignoreParserTestVector(
        "more_asterisks_handled_like_single_asterisk_1",
        ["***a/b"],
        does_match=["/some/dir/XYZa/b"],
        doesnt_match=["/some/dir/foo/a/b"],
    ),
    GitignoreParserTestVector(
        "more_asterisks_handled_like_single_asterisk_2",
        ["a/b***"],
        does_match=["/some/dir/a/bXYZ"],
        doesnt_match=["/some/dir/a/b/foo"],
    ),
    GitignoreParserTestVector(
        "directory_only_negation",
        ["data/**", "!data/**/", "!.gitkeep", "!data/01_raw/*"],
        does_match=["/some/dir/data/02_processed/processed_file.csv"],
        doesnt_match=[
            "/some/dir/data/01_raw/",
            "/some/dir/data/01_raw/.gitkeep",
            "/some/dir/data/01_raw/raw_file.csv",
            "/some/dir/data/02_processed/",
            "/some/dir/data/02_processed/.gitkeep",
        ],
    ),
    GitignoreParserTestVector(
        "single_asterisk",
        ["*"],
        does_match=[
            "/some/dir/file.txt",
            "/some/dir/directory/",
            "/some/dir/directory-trailing/",
        ],
        doesnt_match=[],
    ),
    GitignoreParserTestVector(
        "supports_path_type_argument",
        ["file1", "!file2"],
        does_match=[Path("/some/dir/file1")],
        doesnt_match=[Path("/some/dir/file2")],
    ),
    GitignoreParserTestVector(
        "slash_in_range_does_not_match_dirs",
        ["abc[X-Z/]def"],
        does_match=[
            "/some/dir/abcXdef",
            "/some/dir/abcYdef",
            "/some/dir/abcZdef",
        ],
        doesnt_match=[
            "/some/dir/abcdef",
            "/some/dir/abc/def",
            "/some/dir/abcXYZdef",
        ],
    ),
]


@pytest.mark.parametrize("vector", [pytest.param(v, id=v.id) for v in test_vectors])
def test_gitignore_parser(vector: GitignoreParserTestVector):
    base_dir = Path(vector.base_dir)
    rules = list(
        parse_gitignore_lines(vector.patterns, base_dir, base_dir / ".gitignore")
    )
    # Use a trailing '/' in the test vectors to signal is_dir=True.
    # This trailing slash is stripped by Path() in any case.
    for path in vector.does_match:
        assert match_rules(
            rules, Path(path), isinstance(path, str) and path.endswith("/")
        )
    for path in vector.doesnt_match:
        assert not match_rules(
            rules, Path(path), isinstance(path, str) and path.endswith("/")
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
    assert match_rules(rules, link, False)
