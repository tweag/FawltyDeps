"""Verify behavior of gitignore_parser."""

from pathlib import Path
from textwrap import dedent
from typing import Optional

from fawltydeps.gitignore_parser import parse_gitignore_lines


def _parse(data: str, fake_base_dir: Optional[str] = None):
    return parse_gitignore_lines(
        data.split("\n"), fake_base_dir, Path(fake_base_dir, ".gitignore")
    )


def test_simple():
    matches = _parse(
        "\n".join(["__pycache__/", "*.py[cod]"]),
        fake_base_dir="/some/dir",
    )
    assert not matches("/some/dir/main.py")
    assert matches("/some/dir/main.pyc")
    assert matches("/some/dir/dir/main.pyc")
    assert matches("/some/dir/__pycache__")


def test_incomplete_filename():
    matches = _parse("o.py", fake_base_dir="/some/dir")
    assert matches("/some/dir/o.py")
    assert not matches("/some/dir/foo.py")
    assert not matches("/some/dir/o.pyc")
    assert matches("/some/dir/dir/o.py")
    assert not matches("/some/dir/dir/foo.py")
    assert not matches("/some/dir/dir/o.pyc")


def test_wildcard():
    matches = _parse("hello.*", fake_base_dir="/some/dir")
    assert matches("/some/dir/hello.txt")
    assert matches("/some/dir/hello.foobar/")
    assert matches("/some/dir/dir/hello.txt")
    assert matches("/some/dir/hello.")
    assert not matches("/some/dir/hello")
    assert not matches("/some/dir/helloX")


def test_anchored_wildcard():
    matches = _parse("/hello.*", fake_base_dir="/some/dir")
    assert matches("/some/dir/hello.txt")
    assert matches("/some/dir/hello.c")
    assert not matches("/some/dir/a/hello.java")


def test_trailingspaces():
    patterns = [
        "ignoretrailingspace ",
        "notignoredspace\\ ",
        "partiallyignoredspace\\  ",
        "partiallyignoredspace2 \\  ",
        "notignoredmultiplespace\\ \\ \\ ",
    ]
    matches = _parse("\n".join(patterns), fake_base_dir="/some/dir")
    assert matches("/some/dir/ignoretrailingspace")
    assert not matches("/some/dir/ignoretrailingspace ")
    assert matches("/some/dir/partiallyignoredspace ")
    assert not matches("/some/dir/partiallyignoredspace  ")
    assert not matches("/some/dir/partiallyignoredspace")
    assert matches("/some/dir/partiallyignoredspace2  ")
    assert not matches("/some/dir/partiallyignoredspace2   ")
    assert not matches("/some/dir/partiallyignoredspace2 ")
    assert not matches("/some/dir/partiallyignoredspace2")
    assert matches("/some/dir/notignoredspace ")
    assert not matches("/some/dir/notignoredspace")
    assert matches("/some/dir/notignoredmultiplespace   ")
    assert not matches("/some/dir/notignoredmultiplespace")


def test_comment():
    matches = _parse(
        "\n".join(["somematch", "#realcomment", "othermatch", "\\#imnocomment"]),
        fake_base_dir="/some/dir",
    )
    assert matches("/some/dir/somematch")
    assert not matches("/some/dir/#realcomment")
    assert matches("/some/dir/othermatch")
    assert matches("/some/dir/#imnocomment")


def test_ignore_directory():
    matches = _parse(".venv/", fake_base_dir="/some/dir")
    assert matches("/some/dir/.venv")
    assert matches("/some/dir/.venv/folder")
    assert matches("/some/dir/.venv/file.txt")
    assert not matches("/some/dir/.venv_other_folder")
    assert not matches("/some/dir/.venv_no_folder.py")


def test_ignore_directory_asterisk():
    matches = _parse(".venv/*", fake_base_dir="/some/dir")
    assert not matches("/some/dir/.venv")
    assert matches("/some/dir/.venv/folder")
    assert matches("/some/dir/.venv/file.txt")


def test_negation():
    matches = _parse(
        dedent(
            """
            *.ignore
            !keep.ignore
            """
        ),
        fake_base_dir="/some/dir",
    )
    assert matches("/some/dir/trash.ignore")
    assert not matches("/some/dir/keep.ignore")
    assert matches("/some/dir/waste.ignore")


def test_literal_exclamation_mark():
    matches = _parse(
        "\\!ignore_me!", fake_base_dir="/some/dir"
    )
    assert matches("/some/dir/!ignore_me!")
    assert not matches("/some/dir/ignore_me!")
    assert not matches("/some/dir/ignore_me")


def test_double_asterisks():
    matches = _parse("foo/**/Bar", fake_base_dir="/some/dir")
    assert matches("/some/dir/foo/hello/Bar")
    assert matches("/some/dir/foo/world/Bar")
    assert matches("/some/dir/foo/Bar")
    assert not matches("/some/dir/foo/BarBar")


def test_double_asterisk_without_slashes_handled_like_single_asterisk():
    matches = _parse("a/b**c/d", fake_base_dir="/some/dir")
    assert matches("/some/dir/a/bc/d")
    assert matches("/some/dir/a/bXc/d")
    assert matches("/some/dir/a/bbc/d")
    assert matches("/some/dir/a/bcc/d")
    assert not matches("/some/dir/a/bcd")
    assert not matches("/some/dir/a/b/c/d")
    assert not matches("/some/dir/a/bb/cc/d")
    assert not matches("/some/dir/a/bb/XX/cc/d")


def test_more_asterisks_handled_like_single_asterisk():
    matches = _parse("***a/b", fake_base_dir="/some/dir")
    assert matches("/some/dir/XYZa/b")
    assert not matches("/some/dir/foo/a/b")
    matches = _parse("a/b***", fake_base_dir="/some/dir")
    assert matches("/some/dir/a/bXYZ")
    assert not matches("/some/dir/a/b/foo")


def test_directory_only_negation():
    matches = _parse(
        dedent(
            """
            data/**
            !data/**/
            !.gitkeep
            !data/01_raw/*
            """
        ),
        fake_base_dir="/some/dir",
    )
    assert not matches("/some/dir/data/01_raw/")
    assert not matches("/some/dir/data/01_raw/.gitkeep")
    assert not matches("/some/dir/data/01_raw/raw_file.csv")
    assert not matches("/some/dir/data/02_processed/")
    assert not matches("/some/dir/data/02_processed/.gitkeep")
    assert matches("/some/dir/data/02_processed/processed_file.csv")


def test_single_asterisk():
    matches = _parse("*", fake_base_dir="/some/dir")
    assert matches("/some/dir/file.txt")
    assert matches("/some/dir/directory")
    assert matches("/some/dir/directory-trailing/")


def test_supports_path_type_argument():
    matches = _parse(
        "file1\n!file2", fake_base_dir="/some/dir"
    )
    assert matches(Path("/some/dir/file1"))
    assert not matches(Path("/some/dir/file2"))


def test_slash_in_range_does_not_match_dirs():
    matches = _parse("abc[X-Z/]def", fake_base_dir="/some/dir")
    assert not matches("/some/dir/abcdef")
    assert matches("/some/dir/abcXdef")
    assert matches("/some/dir/abcYdef")
    assert matches("/some/dir/abcZdef")
    assert not matches("/some/dir/abc/def")
    assert not matches("/some/dir/abcXYZdef")


def test_symlink_to_another_directory(tmp_path):
    project_dir = tmp_path / "project_dir"
    link = project_dir / "link"
    target = tmp_path / "another_dir/target"

    project_dir.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)

    matches = _parse("link", fake_base_dir=project_dir)
    # Verify behavior according to https://git-scm.com/docs/gitignore#_notes:
    # Symlinks are not followed and are matched as if they were regular files.
    assert matches(link)
