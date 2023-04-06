"""Verify behavior of packages resolver"""

from typing import Dict, List, Optional

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from fawltydeps.packages import DependenciesMapping, Package, resolve_dependencies


def dict_subset_strategy(input_dict):
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
user_defined_deps = {"apache-airflow": ["airflow"]}
user_defined_strategy = dict_subset_strategy(user_defined_deps)

# user-defined mapping
user_defined_mapping = "\n".join(
    [f'{dep} = ["{",".join(imports)}"]' for dep, imports in user_defined_deps.items()]
)

user_mappings = st.one_of(st.none(), st.just(user_defined_mapping))

# Generate random boolean values
identity_mappings = st.booleans()


def generate_expected_resolved_deps(
    locally_installed_deps: Optional[Dict[str, List[str]]] = None,
    non_locally_installed_deps: Optional[List[str]] = None,
    user_defined_deps: Optional[Dict[str, List[str]]] = None,
    identity_mapping: bool = True,
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
        ret.update(
            {
                dep: Package(
                    dep,
                    {DependenciesMapping.USER_DEFINED: set(imports)},
                )
                for dep, imports in user_defined_deps.items()
            }
        )
    if non_locally_installed_deps:
        if identity_mapping:
            ret.update(
                {
                    dep: Package(dep, {DependenciesMapping.IDENTITY: {dep}})
                    for dep in non_locally_installed_deps
                }
            )
        else:
            ret.update(
                {
                    dep: Package(dep, {DependenciesMapping.UNRESOLVED: set()})
                    for dep in non_locally_installed_deps
                }
            )
    return ret


# Suppressing the warning on function scoped fixtures: even if the tmp writing
# fixture only runs once for all the test cases, it will be writing the same
# content
@given(
    identity_mapping=identity_mappings,
    user_mapping=user_mappings,
    non_installed_deps=non_locally_installed_strategy,
    user_deps=user_defined_strategy,
    installed_deps=locally_installed_strategy,
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_resolve_dependencies__generates_expected_mappings(
    user_deps,
    installed_deps,
    non_installed_deps,
    user_mapping,
    identity_mapping,
    write_tmp_files,
):

    # The case where there are user-defined deps but no user-defined mapping
    # provided is not valid
    assume(not (len(user_deps) > 0 and user_mapping is None))

    dep_names = (
        list(installed_deps.keys()) + list(user_deps.keys()) + non_installed_deps
    )

    # set user_mapping_path
    user_mapping_path = None
    if user_mapping is not None:
        tmp_path = write_tmp_files({"mapping.toml": user_mapping})
        user_mapping_path = tmp_path / "mapping.toml"

    expected = generate_expected_resolved_deps(
        locally_installed_deps=installed_deps,
        non_locally_installed_deps=non_installed_deps,
        user_defined_deps=user_deps,
        identity_mapping=identity_mapping,
    )
    obtained = resolve_dependencies(
        dep_names,
        custom_mapping_path=user_mapping_path,
        identity_mapping=identity_mapping,
    )
    assert obtained == expected
