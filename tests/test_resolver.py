"""Verify behavior of packages resolver"""

import tempfile
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

# non locally installed deps
non_locally_installed_deps = ["pandas", "numpy", "other"]
non_locally_installed_strategy = st.lists(
    st.sampled_from(non_locally_installed_deps), unique=True
)

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

user_file_mapping_strategy = st.one_of(st.none(), st.just(user_mapping_in_file))
user_config_mapping_strategy = st.one_of(st.none(), st.just(user_mapping_in_config))


def user_mapping_to_file_content(user_mapping: Dict[str, List[str]]) -> str:
    return "\n".join(
        [f'{dep} = ["{",".join(imports)}"]' for dep, imports in user_mapping.items()]
    )


def generate_expected_resolved_deps(
    locally_installed_deps: Optional[Dict[str, List[str]]] = None,
    non_locally_installed_deps: Optional[List[str]] = None,
    user_defined_deps: Optional[List[str]] = None,
    user_mapping_from_file: Optional[Dict[str, List[str]]] = None,
    user_mapping_from_config: Optional[Dict[str, List[str]]] = None,
):
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
        with tempfile.NamedTemporaryFile(mode="w+", delete=True) as temp_file:
            if user_mapping_from_file is not None:
                temp_file.write(user_mapping_to_file_content(user_mapping_from_file))
                temp_file.flush()
                temp_file_paths = set([Path(temp_file.name)])
            else:
                temp_file_paths = None
            user_mapping = UserDefinedMapping(temp_file_paths, user_mapping_from_config)
            resolved_packages = user_mapping.lookup_packages(set(user_defined_deps))
            ret.update(resolved_packages)
    if non_locally_installed_deps:
        ret.update(
            {
                dep: Package(dep, {DependenciesMapping.IDENTITY: {dep}})
                for dep in non_locally_installed_deps
            }
        )
    return ret


# Suppressing the warning on function scoped fixtures: even if the tmp writing
# fixture only runs once for all the test cases, it will be writing the same
# content
@given(
    user_config_mapping=user_config_mapping_strategy,
    user_file_mapping=user_file_mapping_strategy,
    non_installed_deps=non_locally_installed_strategy,
    user_deps=user_defined_strategy,
    installed_deps=locally_installed_strategy,
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_resolve_dependencies__generates_expected_mappings(
    user_deps,
    installed_deps,
    non_installed_deps,
    user_config_mapping,
    user_file_mapping,
    tmp_path,
):

    # The case where there are user-defined deps but no user-defined mapping
    # provided is not valid
    assume(
        not (
            len(user_deps) > 0
            and user_config_mapping is None
            and user_file_mapping is None
        )
    )

    dep_names = list(installed_deps.keys()) + user_deps + non_installed_deps

    if user_file_mapping:
        custom_mapping_file = tmp_path / "mapping.toml"
        custom_mapping_file.write_text(user_mapping_to_file_content(user_file_mapping))
    else:
        custom_mapping_file = None

    expected = generate_expected_resolved_deps(
        locally_installed_deps=installed_deps,
        non_locally_installed_deps=non_installed_deps,
        user_defined_deps=user_deps,
        user_mapping_from_config=user_config_mapping,
        user_mapping_from_file=user_file_mapping,
    )

    obtained = resolve_dependencies(
        dep_names,
        custom_mapping_files=set([custom_mapping_file]) if custom_mapping_file else None,
        custom_mapping=user_config_mapping,
    )

    assert obtained == expected
