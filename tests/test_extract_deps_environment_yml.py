"""Test extracting dependencies from environment.yml."""

import logging
from dataclasses import dataclass, field
from typing import List

import pytest

from fawltydeps.extract_deps.environment_yml_parser import parse_environment_yml
from fawltydeps.types import DeclaredDependency, Location


@pytest.mark.parametrize(
    ("environment_yml", "expected_deps"),
    [
        pytest.param(
            """\
            name: my_conda_project
            """,
            [],
            id="no_deps1",
        ),
        pytest.param(
            """\
            name: my_conda_project
            dependencies:
            """,
            [],
            id="no_deps2",
        ),
        pytest.param(
            """\
            name: my_conda_project
            dependencies:
              - python=3.8
              - requests
            """,
            ["requests"],
            id="simple_example_with_python_and_requests",
        ),
        pytest.param(
            """\
            name: my_conda_project
            channels:
              - defaults
            dependencies:
              - python=3.8
              - numpy
              - pandas
            prefix: /home/user/.conda/envs/my_conda_project
            """,
            ["numpy", "pandas"],
            id="result_of_default_conda_env_export_from_history",
        ),
        pytest.param(
            """\
            name: my_conda_project
            channels:
              - defaults
            dependencies:
              - _libgcc_mutex=0.1=main
              - _openmp_mutex=5.1=1_gnu
              - brotli-python=1.0.9=py38h6a678d5_8
              - ca-certificates=2024.7.2=h06a4308_0
              - certifi=2024.7.4=py38h06a4308_0
              - charset-normalizer=3.3.2=pyhd3eb1b0_0
              - idna=3.7=py38h06a4308_0
              - ld_impl_linux-64=2.38=h1181459_1
              - libffi=3.4.4=h6a678d5_1
              - libgcc-ng=11.2.0=h1234567_1
              - libgomp=11.2.0=h1234567_1
              - libstdcxx-ng=11.2.0=h1234567_1
              - ncurses=6.4=h6a678d5_0
              - openssl=3.0.14=h5eee18b_0
              - pip=24.2=py38h06a4308_0
              - pysocks=1.7.1=py38h06a4308_0
              - python=3.8.19=h955ad1f_0
              - readline=8.2=h5eee18b_0
              - requests=2.32.3=py38h06a4308_0
              - setuptools=72.1.0=py38h06a4308_0
              - sqlite=3.45.3=h5eee18b_0
              - tk=8.6.14=h39e8969_0
              - urllib3=2.2.2=py38h06a4308_0
              - wheel=0.43.0=py38h06a4308_0
              - xz=5.4.6=h5eee18b_1
              - zlib=1.2.13=h5eee18b_1
            prefix: /home/user/.conda/envs/my_conda_project
            """,
            [
                "_libgcc_mutex",
                "_openmp_mutex",
                "brotli-python",
                "ca-certificates",
                "certifi",
                "charset-normalizer",
                "idna",
                "ld_impl_linux-64",
                "libffi",
                "libgcc-ng",
                "libgomp",
                "libstdcxx-ng",
                "ncurses",
                "openssl",
                "pip",
                "pysocks",
                # "python",  # is ignored
                "readline",
                "requests",
                "setuptools",
                "sqlite",
                "tk",
                "urllib3",
                "wheel",
                "xz",
                "zlib",
            ],
            id="result_of_default_conda_env_export",
        ),
        pytest.param(
            """\
            name: example

            dependencies:
              - jupyterlab=1.0
              - matplotlib=3.1
              - pandas=0.24
              - scikit-learn=0.21
              - pip=19.1
              - pip:
                - kaggle==1.5
                - yellowbrick==0.9
            """,
            [
                # Conda deps
                "jupyterlab",
                "matplotlib",
                "pandas",
                "scikit-learn",
                "pip",
                # Pip deps
                "kaggle",
                "yellowbrick",
            ],
            id="mixed_conda_and_pip_deps",
        ),
        pytest.param(
            """\
            name: example

            dependencies:
              - scikit-learn=0.21
              - pip=19.1
              - pip:
            """,
            ["scikit-learn", "pip"],
            id="mixed_conda_and_zero_pip_deps",
        ),
        pytest.param(
            """\
            # To set up a development environment using conda, run:
            #
            #   conda env create -f environment.yml
            #   conda activate cartopy-dev
            #   pip install -e .
            #
            name: cartopy-dev
            channels:
              - conda-forge
            dependencies:
              - cython>=0.29.28
              - numpy>=1.23
              - shapely>=2.0
              - pyshp>=2.3
              - pyproj>=3.3.1
              - packaging>=21
              # The testing label has the proper version of freetype included
              - conda-forge/label/testing::matplotlib-base>=3.6

              # OWS
              - owslib>=0.27
              - pillow>=9.1
              # Plotting
              - scipy>=1.9
              # Testing
              - pytest
              - pytest-mpl
              - pytest-xdist
              # Documentation
              - pydata-sphinx-theme
              - sphinx
              - sphinx-gallery
              # Extras
              - pre-commit
              - pykdtree
              - ruff
              - setuptools_scm
            """,
            [
                "cython",
                "numpy",
                "shapely",
                "pyshp",
                "pyproj",
                "packaging",
                "matplotlib-base",
                "owslib",
                "pillow",
                "scipy",
                "pytest",
                "pytest-mpl",
                "pytest-xdist",
                "pydata-sphinx-theme",
                "sphinx",
                "sphinx-gallery",
                "pre-commit",
                "pykdtree",
                "ruff",
                "setuptools_scm",
            ],
            id="cartopy_example",
        ),
    ],
)
def test_parse_environment_yml__wellformed_dependencies__yields_dependencies(
    write_tmp_files, environment_yml, expected_deps
):
    tmp_path = write_tmp_files({"environment.yml": environment_yml})
    path = tmp_path / "environment.yml"

    result = list(parse_environment_yml(path))
    expected = [DeclaredDependency(dep, Location(path)) for dep in expected_deps]
    assert result == expected


@dataclass
class CondaTestVector:
    """Test vectors for parsing of malformed environment.yml."""

    id: str
    data: str
    error_msg_fragment: str
    expect: List[str] = field(default_factory=list)


conda_tests_malformed_samples = [
    CondaTestVector(
        id="invalid_yaml",
        data="],,{This is not valid YAML...\n",
        error_msg_fragment="Failed to parse {path}: ",
    ),
    CondaTestVector(
        id="invalid_top_level_type_str",
        data="This is not a valid environment.yml...\n",
        error_msg_fragment="Failed to parse {path}: No top-level mapping found!",
    ),
    CondaTestVector(
        id="invalid_top_level_type_num",
        data="123\n",
        error_msg_fragment="Failed to parse {path}: No top-level mapping found!",
    ),
    CondaTestVector(
        id="invalid_top_level_type_sequence",
        data="""\
            - foo
            - bar
            """,
        error_msg_fragment="Failed to parse {path}: No top-level mapping found!",
    ),
    CondaTestVector(
        id="invalid_dependencies_type_str",
        data="""\
            dependencies: foobar
            """,
        error_msg_fragment="Failed to parse Conda dependencies in {path}: Not a sequence: ",
    ),
    CondaTestVector(
        id="invalid_dependencies_type_mapping",
        data="""\
            dependencies:
              - foo: 123
                bar: 456
            """,
        error_msg_fragment="Failed to parse Conda dependencies in {path}: Not a string: ",
    ),
    CondaTestVector(
        id="invalid_pip_dependencies_type_str",
        data="""\
            dependencies:
              - pip: foobar
            """,
        error_msg_fragment="Failed to parse Pip dependencies in {path}: Not a sequence: ",
    ),
    CondaTestVector(
        id="invalid_pip_dependencies_type_mapping",
        data="""\
            dependencies:
              - foo
              - bar
              - pip:
                - foo: 123
                  bar: 456
            """,
        error_msg_fragment="Failed to parse Pip dependencies in {path}: Not a string: ",
        expect=["foo", "bar"],
    ),
    CondaTestVector(
        id="invalid_dependencies_malformed_names",
        data="""\
            dependencies:
              - ">foo<"
              - "bar"
            """,
        error_msg_fragment="Failed to parse Conda dependencies in {path}: Expected package name at the start of dependency specifier",
        expect=["bar"],
    ),
    CondaTestVector(
        id="invalid_dependencies_malformed_names",
        data="""\
            dependencies:
              - "pip":
                - "~foo"
                - "bar"
            """,
        error_msg_fragment="Failed to parse Pip dependencies in {path}: Expected package name at the start of dependency specifier",
        expect=["bar"],
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in conda_tests_malformed_samples]
)
def test_parse_environment_yml__malformed_deps__yields_no_deps(
    write_tmp_files, caplog, vector
):
    tmp_path = write_tmp_files({"environment.yml": vector.data})
    path = tmp_path / "environment.yml"

    caplog.set_level(logging.ERROR)
    result = list(parse_environment_yml(path))
    expected_deps = [DeclaredDependency(dep, Location(path)) for dep in vector.expect]
    assert result == expected_deps
    assert vector.error_msg_fragment.format(path=path) in caplog.text


@pytest.mark.parametrize(
    ("environment_yml", "expected", "expected_field_types"),
    [
        pytest.param(
            """\
            name: foo
            """,
            [],
            {"Conda"},
            id="missing_deps",
        ),
        pytest.param(
            """\
            name: foo
            dependencies:
            """,
            [],
            {"Conda"},
            id="missing_deps_contents",
        ),
        pytest.param(
            """\
            name: foo
            dependencies:
              - bar
              - pip:
            """,
            ["bar"],
            {"Pip"},
            id="missing_pip_deps_contents",
        ),
    ],
)
def test_parse_environment_yml__missing_dependencies__logs_debug_message(
    write_tmp_files, caplog, tmp_path, environment_yml, expected, expected_field_types
):
    tmp_path = write_tmp_files({"environment.yml": environment_yml})
    path = tmp_path / "environment.yml"

    caplog.set_level(logging.DEBUG)
    result = list(parse_environment_yml(path))
    expected_deps = [DeclaredDependency(dep, Location(path)) for dep in expected]
    assert expected_deps == result
    for field_type in expected_field_types:
        assert f"Failed to find {field_type} dependencies in {path}" in caplog.text
