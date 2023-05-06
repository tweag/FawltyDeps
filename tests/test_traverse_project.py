"""Test that we can traverse a project to find our inputs."""
import dataclasses
from pathlib import Path
from typing import Optional, Set, Type

import pytest

from fawltydeps.settings import ParserChoice, Settings
from fawltydeps.traverse_project import find_sources
from fawltydeps.types import (
    CodeSource,
    DepsSource,
    PathOrSpecial,
    UnparseablePathException,
)

from .test_sample_projects import SAMPLE_PROJECTS_DIR


@dataclasses.dataclass
class TraverseProjectVector:
    """Test vectors for traverse_project.find_sources()."""

    id: str
    project: str  # The base path for this test, relative to SAMPLE_PROJECTS_DIR
    # The following sets contain paths that are all relative to cwd
    code: Set[str] = dataclasses.field(default_factory=lambda: {"."})
    deps: Set[str] = dataclasses.field(default_factory=lambda: {"."})
    pyenvs: Set[str] = dataclasses.field(default_factory=lambda: {"."})
    deps_parser_choice: Optional[ParserChoice] = None
    expect_imports_src: Set[str] = dataclasses.field(default_factory=set)
    expect_deps_src: Set[str] = dataclasses.field(default_factory=set)
    expect_raised: Optional[Type[Exception]] = None


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
        expect_raised=UnparseablePathException,
    ),
    TraverseProjectVector(
        "given_code_as_non_py_file__raises_exception",
        "blog_post_example",
        code={"README.md"},
        deps=set(),
        pyenvs=set(),
        expect_raised=UnparseablePathException,
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
        expect_raised=UnparseablePathException,
    ),
    TraverseProjectVector(
        "given_deps_as_non_deps_file__raises_exception",
        "blog_post_example",
        code=set(),
        deps={"README.md"},
        pyenvs=set(),
        expect_raised=UnparseablePathException,
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
        "passing_dot_dir_explicitly__does_traverse_into_it",
        "no_issues",
        code={".venv"},
        deps={".venv"},
        expect_imports_src={
            ".venv/lib/python3.10/site-packages/dummy_package/setup.py",
            ".venv/lib/python3.10/site-packages/dummy_package/code.py",
        },
        expect_deps_src={".venv/lib/python3.10/site-packages/dummy_package/setup.py"},
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in find_sources_vectors]
)
def test_find_sources(vector: TraverseProjectVector):
    project_dir = SAMPLE_PROJECTS_DIR / vector.project
    assert project_dir.is_dir()
    settings = Settings(
        code={
            path if path == "<stdin>" else project_dir / path for path in vector.code
        },
        deps={project_dir / path for path in vector.deps},
        deps_parser_choice=vector.deps_parser_choice,
        pyenvs={project_dir / path for path in vector.pyenvs},
    )
    expect_imports_src = {
        path if path == "<stdin>" else project_dir / path
        for path in vector.expect_imports_src
    }
    expect_deps_src = {project_dir / path for path in vector.expect_deps_src}

    actual_imports_src: Set[PathOrSpecial] = set()
    actual_deps_src: Set[Path] = set()

    if vector.expect_raised is not None:
        with pytest.raises(vector.expect_raised):
            list(find_sources(settings))
        return

    for src in find_sources(settings):
        if isinstance(src, CodeSource):
            actual_imports_src.add(src.path)
        elif isinstance(src, DepsSource):
            actual_deps_src.add(src.path)
        else:
            raise TypeError(src)

    assert actual_imports_src == expect_imports_src
    assert actual_deps_src == expect_deps_src
