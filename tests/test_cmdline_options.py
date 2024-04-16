"""Parametrized property-based tests for command line interface.

Contains a strategy, for generating a CLI commands with
combination of parameters in a randomized order (apart from positional args).

Strategy setup consists of three phases:
1. Collect available CLI options
2. Create an atomic strategy for each of those options
    Each atomic strategy returns list[str] that are appended
    to the list of arguments to `run_fawltydeps_subprocess` function.
3. Create a composite strategy that samples from each atomic
    strategy and combine results into a new strategy used in the actual tests.

The strategy construction can be viewed as a reference
to how the CLI options are expected to be used.
"""

import io
import os
import string
from functools import reduce
from pathlib import Path
from textwrap import dedent
from typing import List

import hypothesis.strategies as st
from hypothesis import given, settings

from fawltydeps.main import main

from .utils import SAMPLE_PROJECTS_DIR, walk_dir

project_with_no_issues = SAMPLE_PROJECTS_DIR / "no_issues"
CODE_STDIN_MARKER = "-"
MAX_NUMBER_OF_CODE_ARGS = 3
MAX_NUMBER_OF_DEPS_ARGS = 2
MAX_IGNORE_ARGS = 2
MAX_VERBOSITY_ARGS = 2

safe_string = st.text(alphabet=string.ascii_letters + string.digits, min_size=1)

# ---------------------------------------------- #
# CLI options available
# ---------------------------------------------- #
actions = [
    "--check",
    "--check-undeclared",
    "--check-unused",
    "--list-imports",
    "--list-deps",
]
output_formats = ["--summary", "--detailed", "--json"]
deps_parser_choice = ["requirements.txt", "setup.py", "setup.cfg", "pyproject.toml"]
example_python_stdin = dedent(
    """\
    from pprint import pprint

    import pandas as pd
    import click
    import tensorflow
"""
)
venvs = [str(project_with_no_issues / ".venv")]
other = ["--generate-toml-config", "--version", "--install-deps"]


# Options below contain paths specific for an input project
def available_code_values(project_dir: Path) -> List[str]:
    return [str(f) for f in walk_dir(project_dir) if f.suffix in {".py", ".ipynb"}] + [
        CODE_STDIN_MARKER
    ]


def available_deps_values(project_dir: Path) -> List[str]:
    return [
        str(f)
        for f in walk_dir(project_dir)
        if f.name in {"setup.cfg", "setup.py", "requirements.txt", "pyproject.toml"}
    ]


# ---------------------------------------------- #
# Derive strategies from available options
#
# Each strategy is of type list[str]
# ---------------------------------------------- #
actions_strategy = st.lists(st.sampled_from(actions), min_size=0, max_size=1)
output_formats_strategy = st.lists(
    st.sampled_from(output_formats), min_size=0, max_size=1
)


def code_option_strategy(paths: List[str]):
    if not paths:
        return st.just([])
    return st.lists(
        st.sampled_from(paths),
        min_size=0,
        max_size=MAX_NUMBER_OF_CODE_ARGS,
    ).map(lambda xs: ["--code", *xs] if xs else [])


def deps_option_strategy(paths: List[str]):
    if not paths:
        return st.just([])
    return st.lists(
        st.sampled_from(paths),
        min_size=0,
        max_size=MAX_NUMBER_OF_DEPS_ARGS,
    ).map(lambda xs: ["--deps", *xs] if xs else [])


ignored_strategy = st.lists(safe_string, min_size=0, max_size=MAX_IGNORE_ARGS)
ignored_undeclared_strategy = ignored_strategy.map(
    lambda xs: ["--ignore-undeclared", *xs] if xs else []
)
ignored_unused_strategy = ignored_strategy.map(
    lambda xs: ["--ignore-unused", *xs] if xs else []
)

deps_parser_choice_strategy = st.one_of(st.sampled_from(deps_parser_choice), st.none())

verbosity_indicator = st.text(
    alphabet=["q", "v"], min_size=1, max_size=MAX_VERBOSITY_ARGS
)
verbosity_strategy = st.lists(
    verbosity_indicator, min_size=0, max_size=MAX_VERBOSITY_ARGS
).map(lambda xs: [f"-{x}" for x in xs])

venv_strategy = st.one_of(st.sampled_from(venvs), st.none()).map(
    lambda x: ["--pyenv", x] if x is not None else []
)


# ---------------------------------------------- #
# Compose available strategies
# ---------------------------------------------- #
@st.composite
def cli_arguments_combinations(draw):
    to_stdin = None

    project_dir = draw(
        st.sampled_from([d for d in SAMPLE_PROJECTS_DIR.iterdir() if d.is_dir()])
    )
    code_paths = available_code_values(project_dir=project_dir)
    dep_paths = available_deps_values(project_dir=project_dir)

    # Dependencies are treated differently, as there is an explicit way
    # to point to a parser that we want fawltydeps to use.
    # Following code ensures that we do not encounter trying to match
    # explicit file with incorrect parser (square in the oval-shaped hole problem)
    drawn_deps = draw(deps_option_strategy(dep_paths))
    deps_parser = []
    drawn_deps_parser = draw(deps_parser_choice_strategy)
    # a simple and not 100% accurate check if deps parser matches explicitly given file
    if drawn_deps_parser is not None and all(
        d.endswith(drawn_deps_parser) for d in drawn_deps
    ):
        deps_parser = ["--deps-parser-choice", drawn_deps_parser]

    strategy = st.permutations(
        [
            draw(actions_strategy),
            draw(output_formats_strategy),
            drawn_deps,
            draw(ignored_undeclared_strategy),
            draw(ignored_unused_strategy),
            deps_parser,
            draw(verbosity_strategy),
            draw(venv_strategy),
        ]
    )
    args = reduce(lambda x, y: x + y, draw(strategy))

    # only `code` option changes to_stdin
    code = draw(code_option_strategy(code_paths))
    if "-" in code:
        to_stdin = example_python_stdin
    args += code

    return (project_dir, args, to_stdin)


@given(cli_arguments=cli_arguments_combinations())
@settings(
    deadline=500,
    max_examples=100,
)
def test_options_interactions__correct_options__does_not_abort(cli_arguments):
    """Check if a combination of valid options makes a valid run of fawltydeps CLI tool."""
    project_dir, drawn_args, to_stdin = cli_arguments
    basepath = (
        [] if {"--code", "--deps"}.issubset(set(drawn_args)) else [str(project_dir)]
    )
    args = basepath + drawn_args

    with Path(os.devnull).open("w") as f_out:
        exit_code = main(cmdline_args=args, stdin=io.StringIO(to_stdin), stdout=f_out)

    assert exit_code in {0, 3, 4}
