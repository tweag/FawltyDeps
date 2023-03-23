"""
Parametrized property-based tests for command line interface.

Contains a strategy, for generating a CLI commands with
combination of parameters in a randomized order (apart from positional args).

Strategy setup consists of three phases:
1. Collect available CLI options
2. Create an atomic strategy for each of those options
    Each atomic strategy returns list[str] that are appended
    to the list of arguments to `run_fawltydeps` function.
3. Create a composite strategy that samples from each atomic
    strategy and combine results into a new strategy used in the actual tests.

The strategy construction can be viewed as a reference
to how the CLI options are expected to be used.
"""
import io
from pathlib import Path
import string
from functools import reduce
from textwrap import dedent
from typing import List

import hypothesis.strategies as st
from hypothesis import given

from fawltydeps.main import main
from fawltydeps.utils import walk_dir

from .utils import SAMPLE_PROJECTS_DIR

project_with_no_issues = SAMPLE_PROJECTS_DIR / "no_issues"
CODE_STDIN_MARKER = "-"
MAX_NUMER_OF_CODE_ARGS = 3
MAX_NUMER_OF_DEPS_ARGS = 2
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


# Options below contain specific paths used in input and a chosen set of dependencies
def available_python_input(project_dir: Path) -> List[str]:
    return [str(f) for f in walk_dir(project_dir) if f.suffix == ".py"] + [
        CODE_STDIN_MARKER
    ]


def available_deps(project_dir: Path) -> List[str]:
    return [str(f) for f in walk_dir(project_dir) if f.name != "expected.toml"]


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
    return st.lists(
        st.sampled_from(paths),
        min_size=0,
        max_size=MAX_NUMER_OF_CODE_ARGS,
    ).map(lambda xs: ["--code"] + xs if xs else [])


def deps_option_strategy(paths: List[str]):
    return st.lists(
        st.sampled_from(paths),
        min_size=0,
        max_size=MAX_NUMER_OF_DEPS_ARGS,
    ).map(lambda xs: ["--deps"] + xs if xs else [])


ignored_strategy = st.lists(safe_string, min_size=0, max_size=MAX_IGNORE_ARGS)
ignored_undeclared_strategy = ignored_strategy.map(
    lambda xs: ["--ignore-undeclared"] + xs if xs else []
)
ignored_unused_strategy = ignored_strategy.map(
    lambda xs: ["--ignore-unused"] + xs if xs else []
)

deps_parser_choice_strategy = st.one_of(
    st.sampled_from(deps_parser_choice), st.none()
).map(lambda x: ["--deps-parser-choice", x] if x is not None else [])

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
    code_paths = available_python_input(project_dir=project_dir)
    dep_paths = available_deps(project_dir=project_dir)
    strategy = st.permutations(
        [
            draw(actions_strategy),
            draw(output_formats_strategy),
            draw(deps_option_strategy(dep_paths)),
            draw(ignored_undeclared_strategy),
            draw(ignored_unused_strategy),
            draw(deps_parser_choice_strategy),
            draw(verbosity_strategy),
            # draw(venv_strategy),
        ]
    )
    args = reduce(lambda x, y: x + y, draw(strategy))

    # only `code` option changes to_stdin
    code = draw(code_option_strategy(code_paths))
    if code is not None:
        if "-" in code:
            to_stdin = example_python_stdin
        args += code

    return (project_dir, args, to_stdin)


@given(cli_arguments=cli_arguments_combinations())
def test_options_interactions__correct_options__give_success_code(cli_arguments):
    """Check if a combination of valid options

    makes a valid run of fawltydeps CLI tool.
    """
    project_dir, drawn_args, to_stdin = cli_arguments
    basepath = (
        [] if {"--code", "--deps"}.issubset(set(drawn_args)) else [str(project_dir)]
    )
    args = basepath + drawn_args

    with open("/dev/null", "w") as f_out:
        exit_code = main(cmdline_args=args, stdin=io.StringIO(to_stdin), stdout=f_out)

    assert exit_code in {0, 3, 4}
