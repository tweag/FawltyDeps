"""Verify behavior of packages resolver"""

from pathlib import Path
from typing import Dict, List, Optional

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from fawltydeps.packages import (
    DependenciesMapping,
    Package,
    UserDefinedMapping,
    resolve_dependencies,
)


def dict_subset_strategy(input_dict):
    """Returns a hypothesis strategy to choose items from a dict."""
    keys_strategy = st.lists(st.sampled_from(list(input_dict.keys())), unique=True)

    def build_dict(keys):
        return {key: input_dict[key] for key in keys}

    return keys_strategy.map(build_dict)


# The deps in each category should be disjoint

# deps that cannot be resolved by a user-defined mapping and are not locally
# installed
other_deps = ["pandas", "numpy", "other"]
other_deps_strategy = st.lists(st.sampled_from(other_deps), unique=True)

# locally installed deps
locally_installed_deps = {
    "setuptools": [
        "_distutils_hack",
        "pkg_resources",
        "setuptools",
    ],
    "pip": ["pip"],
    "isort": ["isort"],
}

locally_installed_strategy = dict_subset_strategy(locally_installed_deps)

# user-defined deps
user_defined_mapping = {"apache-airflow": ["airflow", "foo", "bar"]}

user_defined_deps = list(user_defined_mapping)
user_defined_strategy = st.lists(st.sampled_from(user_defined_deps), unique=True)
# splitting the user-defined mapping dict into 2 disjoint dicts:
# one to be defined in a file and the other to be defined in the config
user_mapping_in_file = {
    dep: [imports[0]] for dep, imports in user_defined_mapping.items()
}
user_mapping_in_config = {
    dep: imports[1:] for dep, imports in user_defined_mapping.items()
}

# Either all the user-defined mapping (in a file or config dict) is included
# or none of it
user_file_mapping_strategy = st.one_of(st.none(), st.just(user_mapping_in_file))
user_config_mapping_strategy = st.one_of(st.none(), st.just(user_mapping_in_config))


def user_mapping_to_file_content(user_mapping: Dict[str, List[str]]) -> str:
    return "\n".join(
        [f'{dep} = ["{",".join(imports)}"]' for dep, imports in user_mapping.items()]
    )


def generate_expected_resolved_deps(
    locally_installed_deps: Optional[Dict[str, List[str]]] = None,
    other_deps: Optional[List[str]] = None,
    user_defined_deps: Optional[List[str]] = None,
    user_mapping_file: Optional[Path] = None,
    user_mapping_from_config: Optional[Dict[str, List[str]]] = None,
):
    """
    Returns a dict of resolved packages.

    This function does not actually resolve its input dependencies.
    It just constructs a valid dict of resolved dependencies that respects
    the category of the dependencies in each argument.
    """
    ret = {}
    if locally_installed_deps:
        ret.update(
            {
                dep: Package(
                    dep,
                    {DependenciesMapping.LOCAL_ENV: set(imports)},
                )
                for dep, imports in locally_installed_deps.items()
            }
        )
    if user_defined_deps:
        user_mapping = UserDefinedMapping(
            set([user_mapping_file]) if user_mapping_file else None,
            user_mapping_from_config,
        )
        resolved_packages = user_mapping.lookup_packages(set(user_defined_deps))
        ret.update(resolved_packages)
    if other_deps:
        ret.update(
            {
                dep: Package(dep, {DependenciesMapping.IDENTITY: {dep}})
                for dep in other_deps
            }
        )
    return ret


# Suppressing the warning on function scoped fixtures: the write_tmp_files
# fixture only runs once for all the test cases. But this is not a problem,
# as the fixture-generated content does not have to be reset between test examples.
# The test function only reads the file content and filters needed input.
@given(
    user_config_mapping=user_config_mapping_strategy,
    user_file_mapping=user_file_mapping_strategy,
    user_deps=user_defined_strategy,
    installed_deps=locally_installed_strategy,
    other_deps=other_deps_strategy,
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_resolve_dependencies__generates_expected_mappings(
    user_deps,
    installed_deps,
    other_deps,
    user_config_mapping,
    user_file_mapping,
    tmp_path,
):

    # The case where the resolved output is expected to contain user-mapped
    # deps, but a user-defined mapping is not provided, is not valid
    assume(
        not (
            len(user_deps) > 0
            and user_config_mapping is None
            and user_file_mapping is None
        )
    )

    dep_names = list(installed_deps.keys()) + user_deps + other_deps

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
    )

    obtained = resolve_dependencies(
        dep_names,
        custom_mapping_files=set([custom_mapping_file])
        if custom_mapping_file
        else None,
        custom_mapping=user_config_mapping,
    )

    assert obtained == expected
