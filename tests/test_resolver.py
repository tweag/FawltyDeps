"""Verify behavior of packages resolver."""

import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from fawltydeps.packages import (
    IdentityMapping,
    Package,
    SysPathPackageResolver,
    TemporaryAutoInstallResolver,
    UserDefinedMapping,
    resolve_dependencies,
    setup_resolvers,
)

from .utils import default_sys_path_env_for_tests, ignore_package_debug_info

# The deps in each category should be disjoint
other_deps = {"leftpadx": {"leftpad"}, "SQLObject": {"sqlobject"}}
user_defined_mapping = {"apache-airflow": ["airflow", "foo", "bar"]}


@st.composite
def dict_subset_strategy(draw, input_dict: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """Returns a hypothesis strategy to choose items from a dict."""
    if not input_dict:
        return {}
    keys = draw(st.lists(st.sampled_from(list(input_dict.keys())), unique=True))
    return {k: input_dict[k] for k in keys}


@st.composite
def sample_dict_keys_and_values_strategy(draw, input_dict: Dict[str, List[str]]):
    """Returns a hypothesis strategy to choose keys and values from a dict."""
    keys = draw(st.lists(st.sampled_from(list(input_dict.keys())), unique=True))
    return {
        key: draw(st.lists(st.sampled_from(input_dict[key]), unique=True))
        for key in keys
    }


@st.composite
def user_mapping_strategy(draw, user_mapping: Dict[str, List[str]]):
    user_mapping_in_file = draw(sample_dict_keys_and_values_strategy(user_mapping))
    user_mapping_in_config = draw(sample_dict_keys_and_values_strategy(user_mapping))

    user_deps = []
    if user_mapping_in_config or user_mapping_in_file:
        drawn_deps = list(
            set.union(
                set(user_mapping_in_file.keys()),
                set(user_mapping_in_config.keys()),
            )
        )
        user_deps = draw(st.lists(st.sampled_from(drawn_deps), min_size=1, unique=True))

    return user_deps, user_mapping_in_file, user_mapping_in_config


def user_mapping_to_file_content(user_mapping: Dict[str, List[str]]) -> str:
    return "\n".join(
        [f'{dep} = ["{",".join(imports)}"]' for dep, imports in user_mapping.items()]
    )


def generate_expected_resolved_deps(
    *,
    locally_installed_deps: Dict[str, Set[str]],
    other_deps: Dict[str, Set[str]],
    user_defined_deps: List[str],
    user_mapping_from_config: Dict[str, List[str]],
    user_mapping_file: Optional[Path] = None,
    install_deps: bool = False,
) -> Dict[str, Package]:
    """Returns a dict of resolved packages.

    This function does not actually resolve its input dependencies.
    It just constructs a valid dict of resolved dependencies that respects
    the category of the dependencies in each argument.
    """
    ret = {
        dep: Package(dep, imports, SysPathPackageResolver)
        for dep, imports in locally_installed_deps.items()
    }
    if user_defined_deps:
        user_mapping = UserDefinedMapping(
            {user_mapping_file} if user_mapping_file else None,
            user_mapping_from_config,
        )
        resolved_packages = user_mapping.lookup_packages(set(user_defined_deps))
        ret.update(resolved_packages)
    if install_deps:
        ret.update(
            {
                dep: Package(dep, imports, TemporaryAutoInstallResolver)
                for dep, imports in other_deps.items()
            }
        )
    else:
        ret.update(
            {
                dep: Package(dep, {Package.normalize_name(dep)}, IdentityMapping)
                for dep in other_deps
            }
        )
    return ret


# Suppressing the warning on function scoped fixtures: the write_tmp_files
# fixture only runs once for all the test cases. But this is not a problem,
# as the fixture-generated content does not have to be reset between test examples.
# The test function only reads the file content and filters needed input.
@pytest.mark.usefixtures("local_pypi")
@given(
    user_mapping=user_mapping_strategy(user_defined_mapping),
    installed_deps=dict_subset_strategy(default_sys_path_env_for_tests),
    other_deps=dict_subset_strategy(other_deps),
    install_deps=st.booleans(),
)
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
    max_examples=50,
)
def test_resolve_dependencies__generates_expected_mappings(
    installed_deps,
    other_deps,
    user_mapping,
    isolate_default_resolver,
    tmp_path,
    install_deps,
    request,
):
    start_time = time.time()

    user_deps, user_file_mapping, user_config_mapping = user_mapping

    # The following should be true as the different categories of deps should be
    # disjoint. A change to these deps that does not respect this condition
    # will break the following assert.
    assert (
        set.intersection(
            set(installed_deps.keys()) if installed_deps else set(),
            set(user_deps) if user_deps else set(),
        )
        == set()
        and set.intersection(
            set(installed_deps.keys()) if installed_deps else set(),
            set(other_deps) if other_deps else set(),
        )
        == set()
    )

    dep_names = list(installed_deps.keys()) + user_deps + list(other_deps.keys())

    if user_file_mapping:
        custom_mapping_file = tmp_path / "mapping.toml"
        custom_mapping_file.write_text(user_mapping_to_file_content(user_file_mapping))
    else:
        custom_mapping_file = None

    expected = generate_expected_resolved_deps(
        user_defined_deps=user_deps,
        user_mapping_from_config=user_config_mapping,
        user_mapping_file=custom_mapping_file,
        locally_installed_deps=installed_deps,
        other_deps=other_deps,
        install_deps=install_deps,
    )

    isolate_default_resolver(installed_deps)

    # If we're using `venv.create()` to create virtualenvs and `pip install` to
    # populate them, we will waste a lot of time recreating and repopulating
    # virtualenvs in these tests. This is not the case for `uv` which caches
    # packages locally, and is simply much faster than venv/pip. Therefore, tell
    # TemporaryAutoInstallResolver to reuse our cached venv, instead of creating
    # a new venv for every test case, but only when we're not using uv...
    if shutil.which("uv") is None:
        cached_venv = Path(
            request.config.cache.mkdir(
                f"fawltydeps_reused_venv_{sys.version_info.major}.{sys.version_info.minor}"
            )
        )
        TemporaryAutoInstallResolver.cached_venv = cached_venv
    try:
        actual = resolve_dependencies(
            dep_names,
            setup_resolvers(
                custom_mapping_files={custom_mapping_file}
                if custom_mapping_file
                else None,
                custom_mapping=user_config_mapping,
                use_current_env=True,
                install_deps=install_deps,
            ),
        )
    finally:
        TemporaryAutoInstallResolver.cached_venv = None

    end_time = time.time()
    elapsed_time = end_time - start_time

    deadline = 5000 if not install_deps else None

    if deadline:
        assert elapsed_time <= deadline, f"Test exceeded deadline of {deadline} ms"

    assert ignore_package_debug_info(actual) == ignore_package_debug_info(expected)
