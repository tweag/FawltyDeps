"""Test that we can traverse a project to find our inputs."""

import dataclasses
import logging
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional, Set, Type

import pytest

from fawltydeps.gitignore_parser import RuleMissing
from fawltydeps.settings import ParserChoice, Settings
from fawltydeps.traverse_project import find_sources
from fawltydeps.types import (
    CodeSource,
    DepsSource,
    PathOrSpecial,
    PyEnvSource,
    UnparseablePathError,
)

from .test_sample_projects import SAMPLE_PROJECTS_DIR
from .utils import assert_unordered_equivalence


@dataclasses.dataclass
class TraverseProjectVector:
    """Test vectors for traverse_project.find_sources()."""

    id: str
    project: str  # The base path for this test, relative to SAMPLE_PROJECTS_DIR
    # These sets contain input paths that are all relative to the above project:
    code: Set[str] = dataclasses.field(default_factory=lambda: {"."})
    deps: Set[str] = dataclasses.field(default_factory=lambda: {"."})
    pyenvs: Set[str] = dataclasses.field(default_factory=lambda: {"."})
    exclude: Set[str] = dataclasses.field(default_factory=lambda: Settings().exclude)
    deps_parser_choice: Optional[ParserChoice] = None
    # These are paths (also relative to the project) that we expect to find:
    expect_imports_src: Set[str] = dataclasses.field(default_factory=set)
    expect_deps_src: Set[str] = dataclasses.field(default_factory=set)
    expect_pyenv_src: Set[str] = dataclasses.field(default_factory=set)
    # These are the exceptions we expect to be raised, or warnings to be logged
    expect_raised: Optional[Type[Exception]] = None
    expect_warnings: List[str] = dataclasses.field(default_factory=list)
    skip_me: Callable[[], Optional[str]] = lambda: None  # noqa: E731


def on_windows(msg: str) -> Callable[[], Optional[str]]:
    """Helper used by .skip_me to skip certain tests on Windows."""
    return lambda: msg if sys.platform.startswith("win") else None


def not_on_windows(msg: str) -> Callable[[], Optional[str]]:
    """Helper used by .skip_me to skip certain tests on non-Windows."""
    return lambda: msg if not sys.platform.startswith("win") else None


find_sources_vectors = [
    TraverseProjectVector(
        "default_traversal_in_empty_project_yields__nothing", "empty"
    ),
    TraverseProjectVector(
        "traverse_nothing_in_non_empty_project__yields_nothing",
        "blog_post_example",
        code=set(),
        deps=set(),
        pyenvs=set(),
    ),
    #
    # Testing 'code' alone:
    #
    TraverseProjectVector(
        "given_code_as_nonexistent_file__raises_exception",
        "blog_post_example",
        code={"missing.py"},
        deps=set(),
        pyenvs=set(),
        expect_raised=UnparseablePathError,
    ),
    TraverseProjectVector(
        "given_code_as_non_py_file__raises_exception",
        "blog_post_example",
        code={"README.md"},
        deps=set(),
        pyenvs=set(),
        expect_raised=UnparseablePathError,
    ),
    TraverseProjectVector(
        "given_code_as_specialpath_stdin__yields_preserved_specialpath_stdin",
        "empty",
        code={"<stdin>"},
        deps=set(),
        pyenvs=set(),
        expect_imports_src={"<stdin>"},
    ),
    TraverseProjectVector(
        "given_code_as_py_file__yields_file",
        "blog_post_example",
        code={"my_script.py"},
        deps=set(),
        pyenvs=set(),
        expect_imports_src={"my_script.py"},
    ),
    TraverseProjectVector(
        "given_code_as_ipynb_file__yields_file",
        "mixed_project",
        code={"subdir1/notebook.ipynb"},
        deps=set(),
        pyenvs=set(),
        expect_imports_src={"subdir1/notebook.ipynb"},
    ),
    TraverseProjectVector(
        "given_code_as_py_and_ipynb_file__yields_both_files",
        "mixed_project",
        code={"subdir1/notebook.ipynb", "subdir2/script.py"},
        deps=set(),
        pyenvs=set(),
        expect_imports_src={"subdir1/notebook.ipynb", "subdir2/script.py"},
    ),
    TraverseProjectVector(
        "given_code_as_stdin_and_files__yields_all",
        "mixed_project",
        code={"<stdin>", "subdir1/notebook.ipynb", "subdir2/script.py"},
        deps=set(),
        pyenvs=set(),
        expect_imports_src={"<stdin>", "subdir1/notebook.ipynb", "subdir2/script.py"},
    ),
    TraverseProjectVector(
        "given_code_as_dir__yields_only_files_within",
        "mixed_project",
        code={"subdir1"},
        deps=set(),
        pyenvs=set(),
        expect_imports_src={"subdir1/notebook.ipynb", "subdir1/script.py"},
    ),
    TraverseProjectVector(
        "given_code_as_dir_and_stdin__yields_files_within_dir_and_stdin",
        "mixed_project",
        code={"subdir1", "<stdin>"},
        deps=set(),
        pyenvs=set(),
        expect_imports_src={"subdir1/notebook.ipynb", "subdir1/script.py", "<stdin>"},
    ),
    TraverseProjectVector(
        "given_code_as_multiple_dirs__yields_files_within_all_dirs",
        "mixed_project",
        code={"subdir1", "subdir2"},
        deps=set(),
        pyenvs=set(),
        expect_imports_src={
            "subdir1/notebook.ipynb",
            "subdir1/script.py",
            "subdir2/notebook.ipynb",
            "subdir2/script.py",
            "subdir2/setup.py",
        },
    ),
    TraverseProjectVector(
        "given_code_as_parent_and_child_dirs__yields_files_within_all_dirs",
        "mixed_project",
        code={".", "subdir2"},
        deps=set(),
        pyenvs=set(),
        expect_imports_src={
            "main.py",
            "subdir1/notebook.ipynb",
            "subdir1/script.py",
            "subdir2/notebook.ipynb",
            "subdir2/script.py",
            "subdir2/setup.py",
        },
    ),
    TraverseProjectVector(
        "given_code_as_file_and_dir__yields_file_and_files_within_dir",
        "mixed_project",
        code={"subdir1", "subdir2/notebook.ipynb"},
        deps=set(),
        pyenvs=set(),
        expect_imports_src={
            "subdir1/notebook.ipynb",
            "subdir1/script.py",
            "subdir2/notebook.ipynb",
        },
    ),
    #
    # Testing 'deps' alone:
    #
    TraverseProjectVector(
        "given_deps_as_nonexistent_file__raises_exception",
        "blog_post_example",
        code=set(),
        deps={"missing_requirements.txt"},
        pyenvs=set(),
        expect_raised=UnparseablePathError,
    ),
    TraverseProjectVector(
        "given_deps_as_non_deps_file__raises_exception",
        "blog_post_example",
        code=set(),
        deps={"README.md"},
        pyenvs=set(),
        expect_raised=UnparseablePathError,
    ),
    TraverseProjectVector(
        "given_deps_as_requirements_txt__yields_file",
        "blog_post_example",
        code=set(),
        deps={"requirements.txt"},
        pyenvs=set(),
        expect_deps_src={"requirements.txt"},
    ),
    TraverseProjectVector(
        "given_deps_as_pyproject_toml__yields_file",
        "mixed_project",
        code=set(),
        deps={"pyproject.toml"},
        pyenvs=set(),
        expect_deps_src={"pyproject.toml"},
    ),
    TraverseProjectVector(
        "given_deps_as_setup_cfg_and_pyproject_toml__yields_both_files",
        "mixed_project",
        code=set(),
        deps={"pyproject.toml", "subdir1/setup.cfg"},
        pyenvs=set(),
        expect_deps_src={"pyproject.toml", "subdir1/setup.cfg"},
    ),
    TraverseProjectVector(
        "given_deps_as_dir__yields_only_files_within",
        "mixed_project",
        code=set(),
        deps={"subdir1"},
        pyenvs=set(),
        expect_deps_src={"subdir1/setup.cfg"},
    ),
    TraverseProjectVector(
        "given_deps_as_multiple_dirs__yields_files_within_all_dirs",
        "mixed_project",
        code=set(),
        deps={"subdir1", "subdir2"},
        pyenvs=set(),
        expect_deps_src={"subdir1/setup.cfg", "subdir2/setup.py"},
    ),
    TraverseProjectVector(
        "given_deps_as_parent_and_child_dirs__yields_files_within_all_dirs",
        "mixed_project",
        code=set(),
        deps={".", "subdir2"},
        pyenvs=set(),
        expect_deps_src={"pyproject.toml", "subdir1/setup.cfg", "subdir2/setup.py"},
    ),
    TraverseProjectVector(
        "given_deps_as_file_and_dir__yields_file_and_files_within_dir",
        "mixed_project",
        code=set(),
        deps={"subdir1", "subdir2/setup.py"},
        pyenvs=set(),
        expect_deps_src={"subdir1/setup.cfg", "subdir2/setup.py"},
    ),
    #
    # Test interaction of 'deps_parser_choice' and 'deps' as file vs dir
    #
    TraverseProjectVector(
        "given_deps_as_files_with_parser_choice__yields_all_files",
        "mixed_project",
        code=set(),
        deps={"pyproject.toml", "subdir1/setup.cfg"},
        pyenvs=set(),
        deps_parser_choice=ParserChoice.REQUIREMENTS_TXT,
        expect_deps_src={"pyproject.toml", "subdir1/setup.cfg"},
    ),
    TraverseProjectVector(
        "given_deps_as_dir_with_parser_choice__yields_only_matching_files",
        "mixed_project",
        code=set(),
        deps={"."},
        pyenvs=set(),
        deps_parser_choice=ParserChoice.SETUP_CFG,
        expect_deps_src={"subdir1/setup.cfg"},
    ),
    TraverseProjectVector(
        "given_deps_as_dir_with_wrong_parser_choice__yields_no_matching_files",
        "mixed_project",
        code=set(),
        deps={"subdir2"},
        pyenvs=set(),
        deps_parser_choice=ParserChoice.REQUIREMENTS_TXT,
        expect_deps_src=set(),
    ),
    #
    # Testing 'code' and 'deps' together
    #
    TraverseProjectVector(
        "default_traversal_in_blog_post_example__yields_one_py_two_deps",
        "blog_post_example",
        expect_imports_src={"my_script.py"},
        expect_deps_src={"requirements.txt", "dev-requirements.txt"},
    ),
    TraverseProjectVector(
        "given_explicit_files_in_blog_post_example__yields_one_py_two_deps",
        "blog_post_example",
        code={"my_script.py"},
        deps={"requirements.txt", "dev-requirements.txt"},
        pyenvs=set(),
        expect_imports_src={"my_script.py"},
        expect_deps_src={"requirements.txt", "dev-requirements.txt"},
    ),
    TraverseProjectVector(
        "given_code_and_deps_as_same_dir__yields_files_within",
        "mixed_project",
        code={"subdir1"},
        deps={"subdir1"},
        pyenvs=set(),
        expect_imports_src={"subdir1/notebook.ipynb", "subdir1/script.py"},
        expect_deps_src={"subdir1/setup.cfg"},
    ),
    TraverseProjectVector(
        "given_code_and_deps_as_same_dir_with_file_both_dep_and_import__yields_files_within",
        "mixed_project",
        code={"subdir2"},
        deps={"subdir2"},
        pyenvs=set(),
        expect_imports_src={
            "subdir2/notebook.ipynb",
            "subdir2/script.py",
            "subdir2/setup.py",
        },
        expect_deps_src={"subdir2/setup.py"},
    ),
    TraverseProjectVector(
        "given_code_and_deps_as_separate_dirs__yields_expected_files",
        "mixed_project",
        code={"subdir1"},
        deps={"subdir2"},
        pyenvs=set(),
        expect_imports_src={"subdir1/notebook.ipynb", "subdir1/script.py"},
        expect_deps_src={"subdir2/setup.py"},
    ),
    TraverseProjectVector(
        "given_code_and_deps_as_parent_and_child_dirs__yields_expected_files",
        "mixed_project",
        code={"subdir1"},
        deps={"."},
        pyenvs=set(),
        expect_imports_src={"subdir1/notebook.ipynb", "subdir1/script.py"},
        expect_deps_src={"pyproject.toml", "subdir1/setup.cfg", "subdir2/setup.py"},
    ),
    #
    # 'code' + 'deps' don't traverse into dot dirs (e.g. .git, .venv) by default
    #
    TraverseProjectVector(
        "default_traversal_in_no_issues__does_not_traverse_into_dot_venv",
        "no_issues",
        pyenvs=set(),
        expect_imports_src={"python_file.py"},
        expect_deps_src={"requirements.txt", "subdir/requirements.txt"},
    ),
    TraverseProjectVector(
        "default_traversal_in_hidden_files__finds_nothing",
        "hidden_files",
    ),
    TraverseProjectVector(
        "passing_dot_files_explicitly__does_find_them",
        "hidden_files",
        code={".hidden.code.py"},
        deps={".hidden.requirements.txt"},
        expect_imports_src={".hidden.code.py"},
        expect_deps_src={".hidden.requirements.txt"},
    ),
    TraverseProjectVector(
        "passing_dot_dir_explicitly__does_traverse_into_it",
        "hidden_files",
        code={".hidden_dir"},
        deps={".hidden_dir"},
        pyenvs=set(),
        expect_imports_src={".hidden_dir/code.py"},
        expect_deps_src={".hidden_dir/requirements.txt"},
    ),
    TraverseProjectVector(
        "passing_parent_dir_and_dot_dir_explicitly__does_traverse_into_it",
        "hidden_files",
        code={".hidden_dir"},
        deps={".hidden_dir"},
        pyenvs={"."},
        expect_imports_src={".hidden_dir/code.py"},
        expect_deps_src={".hidden_dir/requirements.txt"},
    ),
    #
    # Testing 'pyenvs' alone:
    #
    TraverseProjectVector(
        "given_pyenv_as_nonexistent_dir__raises_exception",
        "no_issues",
        code=set(),
        deps=set(),
        pyenvs={".does_not_exist"},
        expect_raised=UnparseablePathError,
    ),
    TraverseProjectVector(
        "given_pyenv_as_non_env_dir__yields_nothing",
        "no_issues",
        code=set(),
        deps=set(),
        pyenvs={"subdir"},
        expect_pyenv_src=set(),
    ),
    TraverseProjectVector(
        "given_pyenv_as_venv_dir__yields_package_dir_within",
        "no_issues",
        code=set(),
        deps=set(),
        pyenvs={".venv"},
        expect_pyenv_src={".venv/lib/python3.10/site-packages"},
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:given_pyenv_as_venv_dir__yields_package_dir_within",
        "no_issues_win",
        code=set(),
        deps=set(),
        pyenvs={".venv"},
        expect_pyenv_src={".venv/Lib/site-packages"},
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    TraverseProjectVector(
        "given_pyenv_as_venv_dir__yields_multiple_package_dirs_within",
        "pyenv_galore",
        code=set(),
        deps=set(),
        pyenvs={"another-venv"},
        expect_pyenv_src={
            "another-venv/lib/python3.8/site-packages",
            "another-venv/lib/python3.11/site-packages",
        },
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:given_pyenv_as_venv_dir__can_only_contain_one_package_dir_within",
        "pyenv_galore_win",
        code=set(),
        deps=set(),
        pyenvs={"another-venv"},
        expect_pyenv_src={"another-venv/Lib/site-packages"},
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    TraverseProjectVector(
        "given_pyenv_as_package_dir__yields_only_one_package_dir_within",
        "pyenv_galore",
        code=set(),
        deps=set(),
        pyenvs={"another-venv/lib/python3.8"},
        expect_pyenv_src={"another-venv/lib/python3.8/site-packages"},
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:given_pyenv_as_package_dir__yields_only_one_package_dir_within",
        "pyenv_galore_win",
        code=set(),
        deps=set(),
        pyenvs={"another-venv/Lib"},
        expect_pyenv_src={"another-venv/Lib/site-packages"},
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    TraverseProjectVector(
        "given_two_pyenvs__yields_all_package_dirs_within_both",
        "pyenv_galore",
        code=set(),
        deps=set(),
        pyenvs={".venv", "__pypackages__"},
        expect_pyenv_src={
            ".venv/lib/python3.10/site-packages",
            "__pypackages__/3.7/lib",
            "__pypackages__/3.10/lib",
        },
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:given_two_pyenvs__yields_all_package_dirs_within_both",
        "pyenv_galore_win",
        code=set(),
        deps=set(),
        pyenvs={".venv", "__pypackages__"},
        expect_pyenv_src={
            ".venv/Lib/site-packages",
            "__pypackages__/3.7/Lib",
            "__pypackages__/3.10/Lib",
        },
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    TraverseProjectVector(
        "given_parent_dir__yields_all_package_dirs_within_all_pyenvs",
        "pyenv_galore",
        code=set(),
        deps=set(),
        expect_pyenv_src={
            ".venv/lib/python3.10/site-packages",
            "__pypackages__/3.7/lib",
            "__pypackages__/3.10/lib",
            "another-venv/lib/python3.8/site-packages",
            "another-venv/lib/python3.11/site-packages",
            "poetry2nix_result/lib/python3.9/site-packages",
        },
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:given_parent_dir__yields_all_package_dirs_within_all_pyenvs",
        "pyenv_galore_win",
        code=set(),
        deps=set(),
        expect_pyenv_src={
            ".venv/Lib/site-packages",
            "__pypackages__/3.7/Lib",
            "__pypackages__/3.10/Lib",
            "another-venv/Lib/site-packages",
        },
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    TraverseProjectVector(
        "given_parent_dir__does_not_find_pyenvs_inside_dot_dir",
        "hidden_files",
        code=set(),
        deps=set(),
        expect_pyenv_src=set(),
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:given_parent_dir__does_not_find_pyenvs_inside_dot_dir",
        "hidden_files_win",
        code=set(),
        deps=set(),
        expect_pyenv_src=set(),
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    TraverseProjectVector(
        "given_dot_dir__finds_pyenvs_inside_dot_dir",
        "hidden_files",
        code=set(),
        deps=set(),
        pyenvs={".venvs"},
        expect_pyenv_src={
            ".venvs/.venv/lib/python3.10/site-packages",
            ".venvs/another-venv/lib/python3.8/site-packages",
            ".venvs/another-venv/lib/python3.11/site-packages",
        },
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:given_dot_dir__finds_pyenvs_inside_dot_dir",
        "hidden_files_win",
        code=set(),
        deps=set(),
        pyenvs={".venvs"},
        expect_pyenv_src={
            ".venvs/.venv/Lib/site-packages",
            ".venvs/another-venv/Lib/site-packages",
        },
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    #
    # Test interaction of 'pyenvs' with 'code' and 'deps':
    #
    TraverseProjectVector(
        "given_parent_dir__code_and_deps_are_never_found_within_pyenvs",
        "pyenv_galore",
        expect_pyenv_src={
            ".venv/lib/python3.10/site-packages",
            "__pypackages__/3.7/lib",
            "__pypackages__/3.10/lib",
            "another-venv/lib/python3.8/site-packages",
            "another-venv/lib/python3.11/site-packages",
            "poetry2nix_result/lib/python3.9/site-packages",
        },
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:given_parent_dir__code_and_deps_are_never_found_within_pyenvs",
        "pyenv_galore_win",
        expect_pyenv_src={
            ".venv/Lib/site-packages",
            "__pypackages__/3.7/Lib",
            "__pypackages__/3.10/Lib",
            "another-venv/Lib/site-packages",
        },
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    TraverseProjectVector(
        "given_one_pyenv__code_and_deps_may_be_found_in_other_pyenvs",
        "pyenv_galore",
        pyenvs={"__pypackages__"},
        expect_imports_src={
            "another-venv/lib/python3.8/site-packages/another_package/__init__.py",
            "another-venv/lib/python3.11/site-packages/another_module.py",
            "another-venv/lib/python3.11/site-packages/setup.py",
            "poetry2nix_result/lib/python3.9/site-packages/some_module.py",
        },
        expect_deps_src={
            "another-venv/lib/python3.11/site-packages/setup.py",
        },
        expect_pyenv_src={
            "__pypackages__/3.7/lib",
            "__pypackages__/3.10/lib",
        },
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:given_one_pyenv__code_and_deps_may_be_found_in_other_pyenvs",
        "pyenv_galore_win",
        pyenvs={"__pypackages__"},
        expect_imports_src={
            "another-venv/Lib/site-packages/another_package/__init__.py",
            "another-venv/Lib/site-packages/another_module.py",
            "another-venv/Lib/site-packages/setup.py",
        },
        expect_deps_src={
            "another-venv/Lib/site-packages/setup.py",
        },
        expect_pyenv_src={
            "__pypackages__/3.7/Lib",
            "__pypackages__/3.10/Lib",
        },
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    TraverseProjectVector(
        "given_multiple_dot_dirs__finds_all_except_code_within_pyenvs",
        "hidden_files",
        code={".", ".hidden_dir", ".venvs", ".hidden.code.py"},
        deps={".", ".hidden_dir", ".venvs", ".hidden.requirements.txt"},
        pyenvs={".", ".hidden_dir", ".venvs"},
        expect_imports_src={
            ".hidden.code.py",
            ".hidden_dir/code.py",
        },
        expect_deps_src={
            ".hidden.requirements.txt",
            ".hidden_dir/requirements.txt",
        },
        expect_pyenv_src={
            ".venvs/.venv/lib/python3.10/site-packages",
            ".venvs/another-venv/lib/python3.8/site-packages",
            ".venvs/another-venv/lib/python3.11/site-packages",
        },
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:given_multiple_dot_dirs__finds_all_except_code_within_pyenvs",
        "hidden_files_win",
        code={".", ".hidden_dir", ".venvs", ".hidden.code.py"},
        deps={".", ".hidden_dir", ".venvs", ".hidden.requirements.txt"},
        pyenvs={".", ".hidden_dir", ".venvs"},
        expect_imports_src={
            ".hidden.code.py",
            ".hidden_dir/code.py",
        },
        expect_deps_src={
            ".hidden.requirements.txt",
            ".hidden_dir/requirements.txt",
        },
        expect_pyenv_src={
            ".venvs/.venv/Lib/site-packages",
            ".venvs/another-venv/Lib/site-packages",
        },
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    #
    # Test invalid 'exclude':
    #
    TraverseProjectVector(
        "empty_exclude_pattern__raises_RuleMissing",
        "empty",
        exclude={"", "\t", "    "},
        expect_raised=RuleMissing,
    ),
    TraverseProjectVector(
        "comment_exclude_pattern__raises_RuleMissing",
        "empty",
        exclude={"# a comment", "# another comment"},
        expect_raised=RuleMissing,
    ),
    TraverseProjectVector(
        "disabling_default_exclude__causes_hidden_files_to_be_found",
        "hidden_files",
        exclude=set(),
        expect_imports_src={
            ".hidden.code.py",
            ".hidden_dir/code.py",
        },
        expect_deps_src={
            ".hidden.requirements.txt",
            ".hidden_dir/requirements.txt",
        },
        expect_pyenv_src={
            ".venvs/.venv/lib/python3.10/site-packages",
            ".venvs/another-venv/lib/python3.8/site-packages",
            ".venvs/another-venv/lib/python3.11/site-packages",
        },
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:disabling_default_excludes__causes_hidden_files_to_be_found",
        "hidden_files_win",
        exclude=set(),
        expect_imports_src={
            ".hidden.code.py",
            ".hidden_dir/code.py",
        },
        expect_deps_src={
            ".hidden.requirements.txt",
            ".hidden_dir/requirements.txt",
        },
        expect_pyenv_src={
            ".venvs/.venv/Lib/site-packages",
            ".venvs/another-venv/Lib/site-packages",
        },
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    TraverseProjectVector(
        "replacing_default_exclude__causes_some_hidden_files_to_be_found",
        "hidden_files",
        exclude={".hidden_dir/"},
        expect_imports_src={".hidden.code.py"},
        expect_deps_src={".hidden.requirements.txt"},
        expect_pyenv_src={
            ".venvs/.venv/lib/python3.10/site-packages",
            ".venvs/another-venv/lib/python3.8/site-packages",
            ".venvs/another-venv/lib/python3.11/site-packages",
        },
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:replacing_default_excludes__causes_some_hidden_files_to_be_found",
        "hidden_files_win",
        exclude={".hidden_dir/"},
        expect_imports_src={".hidden.code.py"},
        expect_deps_src={".hidden.requirements.txt"},
        expect_pyenv_src={
            ".venvs/.venv/Lib/site-packages",
            ".venvs/another-venv/Lib/site-packages",
        },
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    #
    # Test overlap/conflict between given --code/--deps/--pyenv and --exclude
    #
    TraverseProjectVector(
        "customized_excludes_overlaps_with_code_path__warns_about_overlap",
        "hidden_files",
        code={".hidden_dir"},
        deps=set(),
        pyenvs=set(),
        exclude={".hidden_dir/"},
        expect_imports_src={".hidden_dir/code.py"},
        expect_warnings=[".hidden_dir is both requested and excluded. Will include."],
    ),
    TraverseProjectVector(
        "customized_excludes_overlaps_with_deps_path__warns_about_overlap",
        "hidden_files",
        code=set(),
        deps={".hidden_dir", "."},
        pyenvs=set(),
        exclude={".hidden_dir", ".*"},
        expect_deps_src={".hidden_dir/requirements.txt"},
        expect_warnings=[".hidden_dir is both requested and excluded. Will include."],
    ),
    TraverseProjectVector(
        "customized_excludes_overlaps_with_pyenv_path__warns_about_overlap",
        "hidden_files",
        code=set(),
        deps=set(),
        pyenvs={".venvs"},
        exclude={".*envs/"},
        expect_pyenv_src={
            ".venvs/.venv/lib/python3.10/site-packages",
            ".venvs/another-venv/lib/python3.8/site-packages",
            ".venvs/another-venv/lib/python3.11/site-packages",
        },
        expect_warnings=[".venvs is both requested and excluded. Will include."],
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:customized_excludes_overlaps_with_pyenv_path__warns_about_overlap",
        "hidden_files_win",
        code=set(),
        deps=set(),
        pyenvs={".venvs"},
        exclude={".*envs/"},
        expect_pyenv_src={
            ".venvs/.venv/Lib/site-packages",
            ".venvs/another-venv/Lib/site-packages",
        },
        expect_warnings=[".venvs is both requested and excluded. Will include."],
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
    TraverseProjectVector(
        "customized_excludes_overlaps_with_several_paths__warns_once_per_path",
        "hidden_files",
        code={".hidden_dir"},
        deps={".hidden_dir"},
        pyenvs={".venvs"},
        exclude={".hidden*", ".venvs"},
        expect_imports_src={".hidden_dir/code.py"},
        expect_deps_src={".hidden_dir/requirements.txt"},
        expect_pyenv_src={
            ".venvs/.venv/lib/python3.10/site-packages",
            ".venvs/another-venv/lib/python3.8/site-packages",
            ".venvs/another-venv/lib/python3.11/site-packages",
        },
        expect_warnings=[
            ".hidden_dir is both requested and excluded. Will include.",
            ".venvs is both requested and excluded. Will include.",
        ],
        skip_me=on_windows("POSIX-style venvs skipped on Windows"),
    ),
    TraverseProjectVector(
        "Windows:customized_excludes_overlaps_with_several_paths__warns_once_per_path",
        "hidden_files_win",
        code={".hidden_dir"},
        deps={".hidden_dir"},
        pyenvs={".venvs"},
        exclude={".hidden*", ".venvs"},
        expect_imports_src={".hidden_dir/code.py"},
        expect_deps_src={".hidden_dir/requirements.txt"},
        expect_pyenv_src={
            ".venvs/.venv/Lib/site-packages",
            ".venvs/another-venv/Lib/site-packages",
        },
        expect_warnings=[
            ".hidden_dir is both requested and excluded. Will include.",
            ".venvs is both requested and excluded. Will include.",
        ],
        skip_me=not_on_windows("Windows-style venvs skipped on POSIX"),
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in find_sources_vectors]
)
def test_find_sources_with_absolute_paths(vector: TraverseProjectVector, caplog):
    skip_me = vector.skip_me()  # skip this test vector?
    if skip_me is not None:
        pytest.skip(skip_me)

    project_dir = SAMPLE_PROJECTS_DIR / vector.project
    assert project_dir.is_dir()
    settings = Settings(
        code={
            "<stdin>" if path == "<stdin>" else project_dir / path
            for path in vector.code
        },
        deps={project_dir / path for path in vector.deps},
        deps_parser_choice=vector.deps_parser_choice,
        pyenvs={project_dir / path for path in vector.pyenvs},
        exclude=vector.exclude,
    )
    expect_imports_src = {
        "<stdin>" if path == "<stdin>" else project_dir / path
        for path in vector.expect_imports_src
    }
    expect_deps_src = {project_dir / path for path in vector.expect_deps_src}
    expect_pyenv_src = {project_dir / path for path in vector.expect_pyenv_src}

    actual_imports_src: Set[PathOrSpecial] = set()
    actual_deps_src: Set[Path] = set()
    actual_pyenv_src: Set[Path] = set()

    if vector.expect_raised is not None:
        with pytest.raises(vector.expect_raised):
            list(find_sources(settings))
        return

    caplog.set_level(logging.WARNING)
    for src in find_sources(settings):
        if isinstance(src, CodeSource):
            actual_imports_src.add(src.path)
        elif isinstance(src, DepsSource):
            actual_deps_src.add(src.path)
        elif isinstance(src, PyEnvSource):
            actual_pyenv_src.add(src.path)
        else:
            raise TypeError(src)

    assert actual_imports_src == expect_imports_src
    assert actual_deps_src == expect_deps_src
    assert actual_pyenv_src == expect_pyenv_src

    actual_warnings = [
        record.message.replace(f"{project_dir}{os.sep}", "")
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    assert_unordered_equivalence(actual_warnings, vector.expect_warnings)


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in find_sources_vectors]
)
def test_find_sources_with_relative_paths(
    vector: TraverseProjectVector, monkeypatch, caplog
):
    skip_me = vector.skip_me()  # skip this test vector?
    if skip_me is not None:
        pytest.skip(skip_me)

    project_dir = SAMPLE_PROJECTS_DIR / vector.project
    assert project_dir.is_dir()
    monkeypatch.chdir(project_dir)
    settings = Settings(
        code={"<stdin>" if path == "<stdin>" else Path(path) for path in vector.code},
        deps={Path(path) for path in vector.deps},
        deps_parser_choice=vector.deps_parser_choice,
        pyenvs={Path(path) for path in vector.pyenvs},
        exclude=vector.exclude,
    )
    expect_imports_src = {
        "<stdin>" if path == "<stdin>" else Path(path)
        for path in vector.expect_imports_src
    }
    expect_deps_src = {Path(path) for path in vector.expect_deps_src}
    expect_pyenv_src = {Path(path) for path in vector.expect_pyenv_src}

    actual_imports_src: Set[PathOrSpecial] = set()
    actual_deps_src: Set[Path] = set()
    actual_pyenv_src: Set[Path] = set()

    if vector.expect_raised is not None:
        with pytest.raises(vector.expect_raised):
            list(find_sources(settings))
        return

    caplog.set_level(logging.WARNING)
    for src in find_sources(settings):
        if isinstance(src, CodeSource):
            actual_imports_src.add(src.path)
        elif isinstance(src, DepsSource):
            actual_deps_src.add(src.path)
        elif isinstance(src, PyEnvSource):
            actual_pyenv_src.add(src.path)
        else:
            raise TypeError(src)

    assert actual_imports_src == expect_imports_src
    assert actual_deps_src == expect_deps_src
    assert actual_pyenv_src == expect_pyenv_src

    actual_warnings = [
        record.message for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert_unordered_equivalence(actual_warnings, vector.expect_warnings)
