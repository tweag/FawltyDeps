""" Test the determination of strategy to parse dependency declarations. """

import logging
import shutil

import pytest

from fawltydeps.extract_declared_dependencies import (
    parse_source,
    parse_sources,
    validate_deps_source,
)
from fawltydeps.settings import ParserChoice, Settings
from fawltydeps.traverse_project import find_sources
from fawltydeps.types import DepsSource

from .utils import assert_unordered_equivalence, collect_dep_names

PARSER_CHOICE_FILE_NAME_MATCH_GRID = {
    ParserChoice.REQUIREMENTS_TXT: "requirements.txt",
    ParserChoice.SETUP_PY: "setup.py",
    ParserChoice.SETUP_CFG: "setup.cfg",
    ParserChoice.PYPROJECT_TOML: "pyproject.toml",
}
PARSER_CHOICE_FILE_NAME_MISMATCH_GRID = {
    pc: [fn for _pc, fn in PARSER_CHOICE_FILE_NAME_MATCH_GRID.items() if pc != _pc]
    for pc in PARSER_CHOICE_FILE_NAME_MATCH_GRID
}


@pytest.mark.parametrize(
    ["parser_choice", "deps_file_name", "has_log"],
    [
        pytest.param(pc, fn, has_log, id=f"{pc}__{fn}__{has_log}")
        for pc, fn, has_log in [
            (pc, fn, True)
            for pc, filenames in PARSER_CHOICE_FILE_NAME_MISMATCH_GRID.items()
            for fn in filenames
        ]
        + [(pc, fn, False) for pc, fn in PARSER_CHOICE_FILE_NAME_MATCH_GRID.items()]
    ],
)
def test_explicit_parse_strategy__mismatch_yields_appropriate_logging(
    tmp_path, caplog, parser_choice, deps_file_name, has_log
):
    """Logging message should be conditional on mismatch between strategy and filename."""
    deps_path = tmp_path / deps_file_name
    deps_path.touch()
    caplog.set_level(logging.WARNING)
    # Execute here just for side effect (log).
    list(parse_source(DepsSource(deps_path, parser_choice)))
    if has_log:
        assert (
            f"Manually applying parser '{parser_choice}' to dependencies: {deps_path}"
        ) in caplog.text
    else:
        assert caplog.text == ""


@pytest.mark.parametrize(
    ["deps_file_name", "exp_deps"],
    [
        pytest.param(fn, deps, id=fn)
        for fn, deps in [
            ("requirements.txt", ["pandas", "click"]),
            ("setup.py", []),
            ("setup.cfg", ["dependencyA", "dependencyB"]),
            ("pyproject.toml", ["pandas", "pydantic", "pylint"]),
        ]
    ],
)
# pylint: disable=unused-argument
def test_filepath_inference(
    tmp_path,
    project_with_setup_with_cfg_pyproject_and_requirements,
    deps_file_name,
    exp_deps,
):
    """Parser choice finalization function can choose based on deps filename."""
    deps_path = tmp_path / deps_file_name
    assert deps_path.is_file()  # precondition
    src = validate_deps_source(deps_path)
    assert src is not None
    obs_deps = collect_dep_names(parse_source(src))
    assert_unordered_equivalence(obs_deps, exp_deps)


@pytest.mark.parametrize(
    ["parser_choice", "exp_deps"],
    [
        pytest.param(choice, exp, id=f"{choice.name}")
        for choice, exp in [
            (
                ParserChoice.REQUIREMENTS_TXT,
                ["pandas", "click", "black", "sphinx", "pandas", "tensorflow"],
            ),
            (ParserChoice.SETUP_PY, []),
            (ParserChoice.SETUP_CFG, ["dependencyA", "dependencyB"]),
            (ParserChoice.PYPROJECT_TOML, ["pandas", "pydantic", "pylint"]),
        ]
    ],
)
# pylint: disable=unused-argument
def test_extract_from_directory_applies_manual_parser_choice_iff_choice_applies(
    tmp_path,
    project_with_setup_with_cfg_pyproject_and_requirements,
    parser_choice,
    exp_deps,
):
    settings = Settings(code=set(), deps={tmp_path}, deps_parser_choice=parser_choice)
    deps_sources = list(find_sources(settings, {DepsSource}))
    obs_deps = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(obs_deps, exp_deps)


@pytest.mark.parametrize(
    ["parser_choice", "fn1", "fn2", "exp_deps"],
    [
        pytest.param(choice, fn1, fn2, exp, id=f"{choice.name}__{fn1}__{fn2}")
        for choice, fn1, fn2, exp in [
            (
                ParserChoice.REQUIREMENTS_TXT,
                "requirements.txt",
                "setup.py",
                ["pandas", "click"],
            ),
            (ParserChoice.SETUP_PY, "setup.py", "requirements.txt", []),
            (
                ParserChoice.SETUP_CFG,
                "setup.cfg",
                "pyproject.toml",
                ["dependencyA", "dependencyB"],
            ),
            (
                ParserChoice.PYPROJECT_TOML,
                "pyproject.toml",
                "setup.cfg",
                ["pandas", "pydantic", "pylint"],
            ),
        ]
    ],
)
# pylint: disable=unused-argument
# pylint: disable=too-many-arguments
def test_extract_from_file_applies_manual_choice_even_if_mismatched(
    caplog,
    tmp_path,
    project_with_setup_with_cfg_pyproject_and_requirements,
    parser_choice,
    fn1,
    fn2,
    exp_deps,
):
    old_path = tmp_path / fn1
    new_path = tmp_path / fn2
    shutil.move(old_path, new_path)
    caplog.set_level(logging.WARNING)
    obs_deps = collect_dep_names(parse_source(DepsSource(new_path, parser_choice)))
    assert_unordered_equivalence(obs_deps, exp_deps)
    exp_msg = f"Manually applying parser '{parser_choice}' to dependencies: {new_path}"
    assert exp_msg in caplog.text
