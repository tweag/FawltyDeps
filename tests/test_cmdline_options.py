from hypothesis import given
import hypothesis.strategies as st
import pytest
from tests.test_cmdline import run_fawltydeps
from itertools import product
from .utils import SAMPLE_PROJECTS_DIR

project_with_no_issues = SAMPLE_PROJECTS_DIR / "no_issues"

actions = [
    None,
    "--check",
    "--check-undeclared",
    "--check-unused",
    "--list-imports",
    "--list-deps",
]
output_formats = [None, "--summary", "--detailed", "--json"]
positional_arguments = [None, project_with_no_issues]

actions_strategy = st.sampled_from(actions)
output_formats_strategy = st.sampled_from(output_formats)
positional_arguments_strategy = st.sampled_from(positional_arguments)

# @pytest.mark.parametrize("action,output_format", product(actions, output_formats))
@given(
    action=actions_strategy,
    output_format=output_formats_strategy,
    project_path=positional_arguments_strategy,
)
def test_options_interactions__correct_options__give_success_code(
    action, output_format, project_path
):
    """Check if a combination of valid options

    makes a valid run of fawltydeps CLI tool.
    """

    args = [project_path] if project_path is not None else []
    if action is not None:
        args.append(action)
    if output_format is not None:
        args.append(output_format)

    output, errors, returncode = run_fawltydeps(*args)
    assert returncode == 0
