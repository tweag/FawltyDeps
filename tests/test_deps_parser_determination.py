""" Test the determination of strategy to parse dependency declarations. """

import logging
from pathlib import Path

import pytest

from fawltydeps.extract_declared_dependencies import (
    ParserChoice,
    finalize_parse_strategy,
)

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


def mkfile(folder: Path, filename: str) -> Path:
    """'touch' the file at the location defined by given folder and name."""
    fp = folder / filename
    with open(fp, "w"):
        return fp


@pytest.mark.parametrize("parser_choice", list(ParserChoice))
def test__to_cmdl_from_cmdl__are_inverses(parser_choice):
    """The parser choice command-line arg functions are exact inverses."""
    assert ParserChoice.from_cmdl(parser_choice.to_cmdl()) == parser_choice


@pytest.mark.parametrize(
    ["parser_choice", "deps_file_name"],
    [
        (pc, fn)
        for pc, fn_match in PARSER_CHOICE_FILE_NAME_MATCH_GRID.items()
        for fn in [fn_match] + PARSER_CHOICE_FILE_NAME_MISMATCH_GRID[pc]
    ],
)
def test_parse_strategy__explicit_is_always_chosen(
    tmp_path, parser_choice, deps_file_name
):
    """Even when filename doesn't match, explicit parser choice is respected."""
    deps_path = mkfile(tmp_path, deps_file_name)
    assert deps_path.is_file()  # precondition
    assert (
        finalize_parse_strategy(deps_path, parser_choice) == parser_choice.value.execute
    )


@pytest.mark.parametrize(
    ["parser_choice", "deps_file_name", "has_log"],
    [
        (pc, fn, True)
        for pc, filenames in PARSER_CHOICE_FILE_NAME_MISMATCH_GRID.items()
        for fn in filenames
    ]
    + [(pc, fn, False) for pc, fn in PARSER_CHOICE_FILE_NAME_MATCH_GRID.items()],
)
def test_explicit_parse_strategy_mismatch_yields_appropriate_logging(
    tmp_path, caplog, parser_choice, deps_file_name, has_log
):
    """Logging message should be conditional on mismatch between strategy and filename."""
    deps_path = mkfile(tmp_path, deps_file_name)
    caplog.set_level(logging.INFO)
    finalize_parse_strategy(
        deps_path, parser_choice
    )  # Execute here just for effect (log).
    if has_log:
        exp_msg = (
            f"Manually applying parsing strategy {parser_choice.name}, "
            f"which doesn't automatically apply to given path: {deps_path}"
        )
        assert exp_msg in caplog.text
    else:
        assert "" == caplog.text


@pytest.mark.parametrize(
    ["deps_file_name", "exp_parse_choice"],
    [(fn, pc.value.execute) for pc, fn in PARSER_CHOICE_FILE_NAME_MATCH_GRID.items()],
)
def test_filepath_inference(tmp_path, deps_file_name, exp_parse_choice):
    """Parser choice finalization function can choose based on deps filename."""
    deps_path = mkfile(tmp_path, deps_file_name)
    obs_parse_choice = finalize_parse_strategy(deps_path)
    assert obs_parse_choice == exp_parse_choice
