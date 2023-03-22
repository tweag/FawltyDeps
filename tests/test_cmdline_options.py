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
import string
from functools import reduce
from textwrap import dedent

import hypothesis.strategies as st
from hypothesis import given

from fawltydeps.utils import walk_dir
from tests.test_cmdline import run_fawltydeps

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
# Options below are  adjusted to `project_with_no_issues`
# They contain specific paths used in input and a chosen set of dependencies
# TODO - create more general examples of happy path, including
#        indicators of missing imports and dependencies
available_python_input = [
    str(f)
    for f in walk_dir(project_with_no_issues)
    if f.suffix == ".py"
    # ] + [CODE_STDIN_MARKER]  TODO: uncomment after fixing #233
]
# input files currently adjusted to `project_with_no_issues`
available_deps = [
    str(project_with_no_issues),
    str(project_with_no_issues / "requirements.txt"),
    str(project_with_no_issues / "subdir"),
    str(project_with_no_issues / "subdir/requirements.txt")
]
# currently adjusted to `project_with_no_issues` (only requirements.txt available)
deps_parser_choice = [
    "requirements.txt",
]
example_python_stdin = dedent(
    """\
    from pprint import pprint

    import pandas as pd
    import click
    import tensorflow
"""
)
venvs = [str(project_with_no_issues / ".venv")]


# ---------------------------------------------- #
# Derive strategies from available options
#
# Each strategy is of type list[str]
# ---------------------------------------------- #
actions_strategy = st.one_of(st.sampled_from(actions), st.none()).map(
    lambda x: [x] if x is not None else []
)

output_formats_strategy = st.one_of(st.sampled_from(output_formats), st.none()).map(
    lambda x: [x] if x is not None else []
)

code_option_strategy = (
    st.lists(
        st.sampled_from(available_python_input),
        min_size=0,
        max_size=MAX_NUMER_OF_CODE_ARGS,
    ).map(
        lambda xs: ["--code"] + xs if xs else []
    )
)

deps_option_strategy = (
    st.lists(
        st.sampled_from(available_deps),
        min_size=0,
        max_size=MAX_NUMER_OF_DEPS_ARGS,
        # TODO this is a temporary fix, to always result in return code = 0
        # This test is supposed to give a "happy path"
    )
    .filter(lambda x: str(project_with_no_issues) in x or len(x) == 0)
    .map(lambda xs: ["--deps"] + xs if xs else [])
)

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
    lambda x: ["--venv", x] if x is not None else []
)


# ---------------------------------------------- #
# Compose available strategies
# ---------------------------------------------- #
@st.composite
def cli_arguments_combinations(draw):
    to_stdin = None
    strategy = st.permutations(
        [
            draw(actions_strategy),
            draw(output_formats_strategy),
            draw(deps_option_strategy),
            draw(ignored_undeclared_strategy),
            draw(ignored_unused_strategy),
            draw(deps_parser_choice_strategy),
            draw(verbosity_strategy),
            # draw(venv_strategy), commented out due to
            #                      high execution time and planned changes of `--venv`
        ]
    )
    args = reduce(lambda x, y: x + y, draw(strategy))

    # only `code` option changes to_stdin
    code = draw(code_option_strategy)
    if code is not None:
        if "-" in code:
            to_stdin = example_python_stdin
        args += code

    return (args, to_stdin)


@given(cli_arguments=cli_arguments_combinations())
def test_options_interactions__correct_options__give_success_code(cli_arguments):
    """Check if a combination of valid options

    makes a valid run of fawltydeps CLI tool.
    """
    drawn_args, to_stdin = cli_arguments
    args = [str(project_with_no_issues)] + drawn_args

    _, _, returncode = run_fawltydeps(*args, to_stdin=to_stdin)

    assert returncode == 0
