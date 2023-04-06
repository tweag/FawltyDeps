"""Verify behavior of packages resolver"""

from typing import Dict, List, Optional

import pytest

from fawltydeps.packages import DependenciesMapping, Package, resolve_dependencies

# The deps in each category should be disjoint
non_locally_installed_deps = ["pandas", "numpy", "other"]
locally_installed_deps = {
    "setuptools": [
        "_distutils_hack",
        "pkg_resources",
        "setuptools",
    ],
    "pip": ["pip"],
    "isort": ["isort"],
}
user_defined_deps = {"apache-airflow": ["airflow"]}

user_defined_mapping = "\n".join(
    [f'{dep} = ["{",".join(imports)}"]' for dep, imports in user_defined_deps.items()]
)


def generate_expected_resolved_deps(
    locally_installed_deps: Optional[Dict[str, List[str]]] = None,
    non_locally_installed_deps: Optional[List[str]] = None,
    user_defined_deps: Optional[Dict[str, List[str]]] = None,
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
        ret.update(
            {
                dep: Package(dep, {DependenciesMapping.IDENTITY: {dep}})
                for dep in non_locally_installed_deps
            }
        )
    return ret


@pytest.mark.parametrize(
    "dep_names,user_mapping,expected",
    [
        pytest.param([], None, {}, id="no_deps__empty_dict"),
        pytest.param(
            non_locally_installed_deps,
            None,
            generate_expected_resolved_deps(
                non_locally_installed_deps=non_locally_installed_deps
            ),
            id="uninstalled_deps__use_identity_mapping",
        ),
        pytest.param(
            locally_installed_deps,
            None,
            generate_expected_resolved_deps(
                locally_installed_deps=locally_installed_deps
            ),
            id="installed_deps__use_local_env_mapping",
        ),
        pytest.param(
            list(locally_installed_deps.keys()) + non_locally_installed_deps,
            None,
            generate_expected_resolved_deps(
                locally_installed_deps=locally_installed_deps,
                non_locally_installed_deps=non_locally_installed_deps,
            ),
            id="mixed_deps__uses_mixture_of_identity_and_local_env_mapping",
        ),
        pytest.param(
            non_locally_installed_deps
            + list(locally_installed_deps.keys())
            + list(user_defined_deps.keys()),
            user_defined_mapping,
            generate_expected_resolved_deps(
                locally_installed_deps=locally_installed_deps,
                non_locally_installed_deps=non_locally_installed_deps,
                user_defined_deps=user_defined_deps,
            ),
            id="mixed_deps__uses_mixture_of_user_defined_identity_and_local_env_mapping",
        ),
        pytest.param(
            non_locally_installed_deps + list(locally_installed_deps.keys()),
            user_defined_mapping,
            generate_expected_resolved_deps(
                locally_installed_deps=locally_installed_deps,
                non_locally_installed_deps=non_locally_installed_deps,
            ),
            id="mixed_deps__unaffected_by_nonmatching_user_defined_mapping",
        ),
    ],
)
def test_resolve_dependencies__focus_on_mappings(
    dep_names, user_mapping, expected, write_tmp_files
):
    user_mapping_path = None
    if user_mapping is not None:
        tmp_path = write_tmp_files({"mapping.toml": user_mapping})
        user_mapping_path = tmp_path / "mapping.toml"

    assert (
        resolve_dependencies(
            dep_names,
            custom_mapping_path=user_mapping_path,
        )
        == expected
    )
