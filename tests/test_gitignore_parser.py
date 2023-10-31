"""Verify behavior of gitignore_parser."""

from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent
from typing import Optional
from unittest.mock import mock_open, patch

from fawltydeps.gitignore_parser import parse_gitignore


def test_simple():
    matches = _parse_gitignore_string(
        "\n".join(["__pycache__/", "*.py[cod]"]),
        fake_base_dir="/home/michael",
    )
    assert not matches("/home/michael/main.py")
    assert matches("/home/michael/main.pyc")
    assert matches("/home/michael/dir/main.pyc")
    assert matches("/home/michael/__pycache__")


def test_incomplete_filename():
    matches = _parse_gitignore_string("o.py", fake_base_dir="/home/michael")
    assert matches("/home/michael/o.py")
    assert not matches("/home/michael/foo.py")
    assert not matches("/home/michael/o.pyc")
    assert matches("/home/michael/dir/o.py")
    assert not matches("/home/michael/dir/foo.py")
    assert not matches("/home/michael/dir/o.pyc")


def test_wildcard():
    matches = _parse_gitignore_string("hello.*", fake_base_dir="/home/michael")
    assert matches("/home/michael/hello.txt")
    assert matches("/home/michael/hello.foobar/")
    assert matches("/home/michael/dir/hello.txt")
    assert matches("/home/michael/hello.")
    assert not matches("/home/michael/hello")
    assert not matches("/home/michael/helloX")


def test_anchored_wildcard():
    matches = _parse_gitignore_string("/hello.*", fake_base_dir="/home/michael")
    assert matches("/home/michael/hello.txt")
    assert matches("/home/michael/hello.c")
    assert not matches("/home/michael/a/hello.java")


def test_trailingspaces():
    patterns = [
        "ignoretrailingspace ",
        "notignoredspace\\ ",
        "partiallyignoredspace\\  ",
        "partiallyignoredspace2 \\  ",
        "notignoredmultiplespace\\ \\ \\ ",
    ]
    matches = _parse_gitignore_string("\n".join(patterns), fake_base_dir="/home/michael")
    assert matches("/home/michael/ignoretrailingspace")
    assert not matches("/home/michael/ignoretrailingspace ")
    assert matches("/home/michael/partiallyignoredspace ")
    assert not matches("/home/michael/partiallyignoredspace  ")
    assert not matches("/home/michael/partiallyignoredspace")
    assert matches("/home/michael/partiallyignoredspace2  ")
    assert not matches("/home/michael/partiallyignoredspace2   ")
    assert not matches("/home/michael/partiallyignoredspace2 ")
    assert not matches("/home/michael/partiallyignoredspace2")
    assert matches("/home/michael/notignoredspace ")
    assert not matches("/home/michael/notignoredspace")
    assert matches("/home/michael/notignoredmultiplespace   ")
    assert not matches("/home/michael/notignoredmultiplespace")


def test_comment():
    matches = _parse_gitignore_string(
        "\n".join(["somematch", "#realcomment", "othermatch", "\\#imnocomment"]),
        fake_base_dir="/home/michael",
    )
    assert matches("/home/michael/somematch")
    assert not matches("/home/michael/#realcomment")
    assert matches("/home/michael/othermatch")
    assert matches("/home/michael/#imnocomment")


def test_ignore_directory():
    matches = _parse_gitignore_string(".venv/", fake_base_dir="/home/michael")
    assert matches("/home/michael/.venv")
    assert matches("/home/michael/.venv/folder")
    assert matches("/home/michael/.venv/file.txt")
    assert not matches("/home/michael/.venv_other_folder")
    assert not matches("/home/michael/.venv_no_folder.py")


def test_ignore_directory_asterisk():
    matches = _parse_gitignore_string(".venv/*", fake_base_dir="/home/michael")
    assert not matches("/home/michael/.venv")
    assert matches("/home/michael/.venv/folder")
    assert matches("/home/michael/.venv/file.txt")


def test_negation():
    matches = _parse_gitignore_string(
        dedent(
            """
            *.ignore
            !keep.ignore
            """
        ),
        fake_base_dir="/home/michael",
    )
    assert matches("/home/michael/trash.ignore")
    assert not matches("/home/michael/keep.ignore")
    assert matches("/home/michael/waste.ignore")


def test_literal_exclamation_mark():
    matches = _parse_gitignore_string(
        "\\!ignore_me!", fake_base_dir="/home/michael"
    )
    assert matches("/home/michael/!ignore_me!")
    assert not matches("/home/michael/ignore_me!")
    assert not matches("/home/michael/ignore_me")


def test_double_asterisks():
    matches = _parse_gitignore_string("foo/**/Bar", fake_base_dir="/home/michael")
    assert matches("/home/michael/foo/hello/Bar")
    assert matches("/home/michael/foo/world/Bar")
    assert matches("/home/michael/foo/Bar")
    assert not matches("/home/michael/foo/BarBar")


def test_double_asterisk_without_slashes_handled_like_single_asterisk():
    matches = _parse_gitignore_string("a/b**c/d", fake_base_dir="/home/michael")
    assert matches("/home/michael/a/bc/d")
    assert matches("/home/michael/a/bXc/d")
    assert matches("/home/michael/a/bbc/d")
    assert matches("/home/michael/a/bcc/d")
    assert not matches("/home/michael/a/bcd")
    assert not matches("/home/michael/a/b/c/d")
    assert not matches("/home/michael/a/bb/cc/d")
    assert not matches("/home/michael/a/bb/XX/cc/d")


def test_more_asterisks_handled_like_single_asterisk():
    matches = _parse_gitignore_string("***a/b", fake_base_dir="/home/michael")
    assert matches("/home/michael/XYZa/b")
    assert not matches("/home/michael/foo/a/b")
    matches = _parse_gitignore_string("a/b***", fake_base_dir="/home/michael")
    assert matches("/home/michael/a/bXYZ")
    assert not matches("/home/michael/a/b/foo")


def test_directory_only_negation():
    matches = _parse_gitignore_string(
        dedent(
            """
            data/**
            !data/**/
            !.gitkeep
            !data/01_raw/*
            """
        ),
        fake_base_dir="/home/michael",
    )
    assert not matches("/home/michael/data/01_raw/")
    assert not matches("/home/michael/data/01_raw/.gitkeep")
    assert not matches("/home/michael/data/01_raw/raw_file.csv")
    assert not matches("/home/michael/data/02_processed/")
    assert not matches("/home/michael/data/02_processed/.gitkeep")
    assert matches("/home/michael/data/02_processed/processed_file.csv")


def test_single_asterisk():
    matches = _parse_gitignore_string("*", fake_base_dir="/home/michael")
    assert matches("/home/michael/file.txt")
    assert matches("/home/michael/directory")
    assert matches("/home/michael/directory-trailing/")


def test_supports_path_type_argument():
    matches = _parse_gitignore_string(
        "file1\n!file2", fake_base_dir="/home/michael"
    )
    assert matches(Path("/home/michael/file1"))
    assert not matches(Path("/home/michael/file2"))


def test_slash_in_range_does_not_match_dirs():
    matches = _parse_gitignore_string("abc[X-Z/]def", fake_base_dir="/home/michael")
    assert not matches("/home/michael/abcdef")
    assert matches("/home/michael/abcXdef")
    assert matches("/home/michael/abcYdef")
    assert matches("/home/michael/abcZdef")
    assert not matches("/home/michael/abc/def")
    assert not matches("/home/michael/abcXYZdef")


def test_symlink_to_another_directory():
    with TemporaryDirectory() as project_dir, TemporaryDirectory() as another_dir:
        matches = _parse_gitignore_string("link", fake_base_dir=project_dir)

        # Create a symlink to another directory.
        link = Path(project_dir, "link")
        target = Path(another_dir, "target")
        link.symlink_to(target)

        # Check the intended behavior according to
        # https://git-scm.com/docs/gitignore#_notes:
        # Symbolic links are not followed and are matched as if they were
        # regular files.
        assert matches(link)


def _parse_gitignore_string(data: str, fake_base_dir: Optional[str] = None):
    with patch("builtins.open", mock_open(read_data=data)):
        success = parse_gitignore(f"{fake_base_dir}/.gitignore", fake_base_dir)
        return success
