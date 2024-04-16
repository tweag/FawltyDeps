"""Test that dependencies are parsed from requirements files."""

from textwrap import dedent

import pytest

from fawltydeps.extract_declared_dependencies import (
    parse_requirements_txt,
    parse_setup_cfg,
    parse_setup_py,
    parse_sources,
    validate_deps_source,
)
from fawltydeps.settings import Settings
from fawltydeps.traverse_project import find_sources
from fawltydeps.types import DepsSource

from .utils import (
    assert_unordered_equivalence,
    collect_dep_names,
    dedent_bytes,
    deps_factory,
)


@pytest.mark.parametrize(
    ("file_content", "expect_deps"),
    [
        pytest.param(
            """\
            pandas
            click
            """,
            ["pandas", "click"],
            id="simple_requirements_success",
        ),
        pytest.param(
            """\
            pandas

            click >=1.2
            """,
            ["pandas", "click"],
            id="requirements_with_versions__yields_names",
        ),
        pytest.param(
            """\
            requests [security] @ https://github.com/psf/requests/archive/refs/heads/main.zip
            """,
            ["requests"],
            id="requirements_with_url_based_specifier__yields_names",
        ),
        pytest.param(
            """\
            # this is a comment
            click >=1.2
            """,
            ["click"],
            id="requirements_with_comment__ignores_comment",
        ),
        pytest.param(
            """\
            -e .
            click >=1.2
            """,
            ["click"],
            id="requirements_with_option__ignores_option",
        ),
        pytest.param(
            """\
            . # for running tests
            click >=1.2
            """,
            ["click"],
            id="requirements_with_option__ignores_option_Issue200",
        ),
        pytest.param(
            """\
            black == 23.1.0 \
                --hash=sha256:0052dba51dec07ed029ed61b18183942043e00008ec65d5028814afaab9a22fd
            """,
            ["black"],
            id="per_req_option_not_on_same_line__parses_properly_Issue225",
        ),
    ],
)
def test_parse_requirements_txt(write_tmp_files, file_content, expect_deps):
    tmp_path = write_tmp_files({"requirements.txt": file_content})
    path = tmp_path / "requirements.txt"

    expected = deps_factory(*expect_deps, path=path)
    result = list(parse_requirements_txt(path))
    assert_unordered_equivalence(result, expected)


@pytest.mark.parametrize(
    ("file_content", "expect_deps"),
    [
        pytest.param(
            """\
            from setuptools import setup

            setup(
                name="MyLib",
                install_requires=["pandas", "click"]
            )
            """,
            ["pandas", "click"],
            id="simple_requirements_in_setup_py__succeeds",
        ),
        pytest.param(
            """\
            from setuptools import setup

            setup(
                name="MyLib",
                install_requires=["pandas", "click>=1.2"]
            )
            """,
            ["pandas", "click"],
            id="requirements_with_versions__yields_names",
        ),
        pytest.param(
            """\
            from setuptools import setup

            setup(
                name="MyLib"
            )
            """,
            [],
            id="no_requirements__yields_nothing",
        ),
        pytest.param(
            """\
            from setuptools import setup

            def random_version():
                return 42

            setup(
                name="MyLib",
                version=random_version(),
                install_requires=["pandas", "click>=1.2"]
            )
            """,
            ["pandas", "click"],
            id="handles_nested_functions__yields_names",
        ),
        pytest.param(
            """\
            from setuptools import setup

            def myfunc():
                def setup(**kwargs):
                    pass
                setup(
                    name="IncorrectCall",
                    install_requires=["foo"]
                )

            setup(
                name="MyLib",
                version=random_version(),
                install_requires=["pandas", "click>=1.2"]
            )
            """,
            ["pandas", "click"],
            id="two_setup_calls__uses_only_top_level",
        ),
        pytest.param(
            """\
            from setuptools import setup

            setup(
                name="MyLib",
                extras_require={
                    'annoy': ['annoy==1.15.2'],
                    'chinese': ['jieba']
                    }
            )
            """,
            ["annoy", "jieba"],
            id="extras_present__yields_names",
        ),
        pytest.param(
            """\
            from setuptools import setup

            setup(
                name="MyLib",
                install_requires=["pandas", "click>=1.2"],
                extras_require={
                    'annoy': ['annoy==1.15.2'],
                    'chinese': ['jieba']
                    }
            )
            """,
            ["pandas", "click", "annoy", "jieba"],
            id="extras_and_regular_dependencies__yields_all_names",
        ),
        pytest.param(
            """\
            from setuptools import setup

            my_deps = ["pandas", "click"]

            setup(
                name="MyLib",
                install_requires=my_deps,
            )
            """,
            ["pandas", "click"],
            id="direct_list_variable_reference__succeeds",
        ),
        pytest.param(
            """\
            from setuptools import setup

            my_extra_deps = {
                "annoy": ["annoy==1.15.2"],
                "chinese": ["jieba"],
            }

            setup(
                name="MyLib",
                extras_require=my_extra_deps,
            )
            """,
            ["annoy", "jieba"],
            id="direct_dict_variable_reference__succeeds",
        ),
        pytest.param(
            """\
            from setuptools import setup

            pandas = "pandas"
            click = "click"

            setup(
                name="MyLib",
                install_requires=[pandas, click],
            )
            """,
            ["pandas", "click"],
            id="variable_reference_inside_list__succeeds",
        ),
        pytest.param(
            """\
            from setuptools import setup

            annoy = "annoy"
            annoy_deps = ["annoy==1.15.2"]
            foobar = "foobar"

            setup(
                name="MyLib",
                extras_require={
                    annoy: annoy_deps,
                    foobar: [foobar],
                },
            )
            """,
            ["annoy", "foobar"],
            id="variable_reference_inside_dict__succeeds",
        ),
        pytest.param(
            """\
            from setuptools import setup

            pandas = "pandas"
            my_deps = [pandas, "click"]
            annoy = "annoy"
            annoy_deps = ["annoy==1.15.2"]
            foobar = "foobar"
            my_extra_deps = {
                annoy: annoy_deps,
                foobar: [foobar],
            }

            setup(
                name="MyLib",
                install_requires=my_deps,
                extras_require=my_extra_deps,
            )
            """,
            ["pandas", "click", "annoy", "foobar"],
            id="nested_variable_reference__succeeds",
        ),
        pytest.param(
            dedent_bytes(
                b"""\
                # -*- coding: big5 -*-
                from setuptools import setup

                setup(
                    name="\xa4@\xa8\xc7\xa4\xa4\xa4\xe5\xa6r\xb2\xc5",
                    install_requires=["pandas", "click"]
                )
                """
            ),
            ["pandas", "click"],
            id="legacy_encoding__succeeds",
        ),
    ],
)
def test_parse_setup_py(write_tmp_files, file_content, expect_deps):
    tmp_path = write_tmp_files({"setup.py": file_content})
    path = tmp_path / "setup.py"

    expected = deps_factory(*expect_deps, path=path)
    result = list(parse_setup_py(path))
    assert_unordered_equivalence(result, expected)


@pytest.mark.parametrize(
    ("file_content", "expect_deps"),
    [
        pytest.param(
            """\
            [options]
            install_requires =
                pandas
                click
            """,
            ["pandas", "click"],
            id="simple_requirements_in_setup_cfg__succeeds",
        ),
        pytest.param(
            """\
            [metadata]
            license_files = LICENSE
            """,
            [],
            id="no_requirements_in_setup_cfg__returns_none",
        ),
        pytest.param(
            """\
            [options.extras_require]
            test = pytest
            """,
            ["pytest"],
            id="extra_requirements_section_in_setup_cfg__succeeds",
        ),
        pytest.param(
            """\
            [options.tests_require]
            test = pytest
            """,
            ["pytest"],
            id="tests_requirements_section_in_setup_cfg__succeeds",
        ),
        pytest.param(
            """\
            [options]
            tests_require =
                hypothesis
                tox
            """,
            ["hypothesis", "tox"],
            id="tests_requirements_in_setup_cfg__succeeds",
        ),
        pytest.param(
            """\
            [options]
            extras_require =
                hypothesis
                tox
            """,
            ["hypothesis", "tox"],
            id="extras_requirements_in_setup_cfg__succeeds",
        ),
        pytest.param(
            """\
            [options]
            install_requires =
                pandas
                click
            tests_require =
                tox
            extras_require =
                scipy

            [options.extras_require]
            test = pytest

            [options.tests_require]
            test = hypothesis
            """,
            ["pandas", "click", "tox", "scipy", "pytest", "hypothesis"],
            id="all_requirements_types_in_setup_cfg__succeeds",
        ),
    ],
)
def test_parse_setup_cfg(write_tmp_files, file_content, expect_deps):
    tmp_path = write_tmp_files({"setup.cfg": file_content})
    path = tmp_path / "setup.cfg"

    expected = deps_factory(*expect_deps, path=path)
    result = list(parse_setup_cfg(path))
    assert_unordered_equivalence(result, expected)


def test_parse_setup_py__multiple_entries_in_extras_require__returns_list(
    write_tmp_files,
):
    tmp_path = write_tmp_files(
        {
            "setup.py": """\
                from setuptools import setup

                setup(
                    name="MyLib",
                    extras_require={
                        "simple_parsing":["abc"],
                        "bert": [
                            "bert-serving-server>=1.8.6",
                            "bert-serving-client>=1.8.6",
                            "pytorch-transformer",
                            "flair"
                            ],
                        }
                )
                """,
        }
    )
    path = tmp_path / "setup.py"

    expected = deps_factory(
        "abc",
        "bert-serving-server",
        "bert-serving-client",
        "pytorch-transformer",
        "flair",
        path=path,
    )
    result = list(parse_setup_py(path))
    assert_unordered_equivalence(result, expected)


def test_find_and_parse_sources__simple_project__returns_list(fake_project):
    expect = ["pandas", "click", "pandas", "tensorflow"]
    tmp_path = fake_project(
        files_with_declared_deps={
            "requirements.txt": ["pandas", "click"],
            "subdir/requirements.txt": ["pandas", "tensorflow>=2"],
            # This file should be ignored:
            ".venv/requirements.txt": ["foo_package", "bar_package"],
        },
    )
    settings = Settings(code=set(), deps={tmp_path})
    deps_sources = list(find_sources(settings, {DepsSource}))
    actual = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(actual, expect)


def test_find_and_parse_sources__project_with_requirements_and_setup__returns_list(
    project_with_setup_and_requirements,
):
    expect = [
        "pandas",
        "click",
        "pandas",
        "click",
        "annoy",
        "jieba",
        "pandas",
        "tensorflow",
    ]
    settings = Settings(code=set(), deps={project_with_setup_and_requirements})
    deps_sources = list(find_sources(settings, {DepsSource}))
    actual = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(actual, expect)


def test_parse_sources__parse_only_requirements_from_subdir__returns_list(
    project_with_setup_and_requirements,
):
    "In setup.py requirements are read from dict."
    expect = [
        "pandas",
        "tensorflow",
    ]
    path = project_with_setup_and_requirements / "subdir/requirements.txt"
    actual = collect_dep_names(parse_sources([validate_deps_source(path)]))
    assert_unordered_equivalence(actual, expect)


def test_find_and_parse_sources__project_with_pyproject_setup_and_requirements__returns_list(
    fake_project,
):
    tmp_path = fake_project(
        files_with_declared_deps={
            "requirements.txt": ["pandas", "click"],
            "subdir/requirements.txt": ["pandas", "tensorflow>=2"],
            "setup.py": (
                ["pandas", "click>=1.2"],  # install_requires
                {"annoy": ["annoy==1.15.2"], "chinese": ["jieba"]},  # extras_require
            ),
            "pyproject.toml": (
                ["pandas", "pydantic>1.10.4"],  # dependencies
                {"dev": ["pylint >= 2.15.8"]},  # optional-dependencies
            ),
        },
    )
    expect = [
        # from requirements.txt:
        "pandas",
        "click",
        # from subdir/requirements.txt:
        "pandas",
        "tensorflow",
        # from setup.py:
        "pandas",
        "click",
        "annoy",
        "jieba",
        # from pyproject.toml:
        "pandas",
        "pydantic",
        "pylint",
    ]
    settings = Settings(code=set(), deps={tmp_path})
    deps_sources = list(find_sources(settings, {DepsSource}))
    actual = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(actual, expect)


def test_find_and_parse_sources__project_with_pyproject__returns_list(fake_project):
    tmp_path = fake_project(
        files_with_declared_deps={
            "pyproject.toml": (
                ["pandas", "pydantic>1.10.4"],  # dependencies
                {"dev": ["pylint >= 2.15.8"]},  # optional-dependencies
            ),
        },
    )
    expect = [
        "pandas",
        "pydantic",
        "pylint",
    ]
    settings = Settings(code=set(), deps={tmp_path})
    deps_sources = list(find_sources(settings, {DepsSource}))
    actual = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(actual, expect)


def test_find_and_parse_dynamic_sources__project_with_pyproject__returns_list(
    fake_project,
):
    # Write requirements files into a place where files should be initially ignored
    # but will be included when the dynamic sections in pyproject.toml are parsed.
    tmp_path = fake_project(
        files_with_declared_deps={
            ".subdir/requirements.txt": ["pandas"],
            ".subdir/requirements-test.txt": ["pylint >= 2.15.8"],
        },
        extra_file_contents={
            "pyproject.toml": """\
            [project]
            name = "MyLib"
            dynamic = ["dependencies", "optional-dependencies"]
            [tool.setuptools.dynamic]
            dependencies = { file = [".subdir/requirements.txt"] }
            optional-dependencies.test = { file = [".subdir/requirements-test.txt"] } """,
        },
    )
    expect = [
        "pandas",
        "pylint",
    ]
    settings = Settings(code=set(), deps={tmp_path})
    deps_sources = list(find_sources(settings, {DepsSource}))
    actual = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(actual, expect)


def test_find_and_parse_static_and_dynamic_sources__project_with_pyproject__returns_list(
    fake_project,
):
    # Write requirements files into a place where files should be initially ignored
    # but will be included when the dynamic sections in pyproject.toml are parsed.

    # If dependencies or optional dependencies are declared dynamic, they can
    # no longer be declared static. Therefore, the static [project.dependencies]
    # and [project.optional-dependencies] sections will not be parsed since
    # "dependencies" and "optional-dependencies" are declared in [project.dynamic].
    tmp_path = fake_project(
        files_with_declared_deps={
            ".subdir/requirements.txt": ["pandas"],
            ".subdir/requirements-test.txt": ["pylint >= 2.15.8"],
        },
        extra_file_contents={
            "pyproject.toml": """\
            [project]
            name = "MyLib"
            dynamic = ["dependencies", "optional-dependencies"]
            dependencies = ["django"]
            optional-dependencies = {"dev" = ["black"]}
            [tool.setuptools.dynamic]
            dependencies = { file = [".subdir/requirements.txt"] }
            optional-dependencies.test = { file = [".subdir/requirements-test.txt"] } """,
        },
    )
    expect = [
        "pandas",
        "pylint",
    ]
    settings = Settings(code=set(), deps={tmp_path})
    deps_sources = list(find_sources(settings, {DepsSource}))
    actual = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(actual, expect)


def test_find_and_parse_static_and_dynamic_dependencies__project_with_pyproject__returns_list(
    fake_project,
):
    # Write requirements files into a place where files should be initially ignored
    # but will be included when the dynamic sections in pyproject.toml are parsed.

    # If dependencies or optional dependencies are declared dynamic, they can no longer
    # be declared as static. As a result, the [project.dependencies] section won't be parsed,
    # since "dependencies" is declared in [project.dynamic]. However, the static
    # [project.optional-dependencies] section will still be parsed, as "optional-dependencies"
    # is not marked as dynamic.
    tmp_path = fake_project(
        files_with_declared_deps={
            ".subdir/requirements.txt": ["pandas"],
            ".subdir/requirements-test.txt": ["pylint >= 2.15.8"],
        },
        extra_file_contents={
            "pyproject.toml": """\
            [project]
            name = "MyLib"
            dynamic = ["dependencies"]
            dependencies = ["django"]
            optional-dependencies = {"dev" = ["black"]}
            [tool.setuptools.dynamic]
            dependencies = { file = [".subdir/requirements.txt"] }
            optional-dependencies.test = { file = [".subdir/requirements-test.txt"] } """,
        },
    )
    expect = [
        "pandas",
        "black",
    ]
    settings = Settings(code=set(), deps={tmp_path})
    deps_sources = list(find_sources(settings, {DepsSource}))
    actual = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(actual, expect)


def test_find_and_parse_static_and_dynamic_opt_dependencies__project_with_pyproject__returns_list(
    fake_project,
):
    # Write requirements files into a place where files should be initially ignored
    # but will be included when the dynamic sections in pyproject.toml are parsed.

    # If dependencies or optional dependencies are declared dynamic, they can no longer
    # be declared as static. As a result, the [project.optional-dependencies] section
    # won't be parsed, since "optional-dependencies" is declared in [project.dynamic].
    # However, the static [project.dependencies] section will still be parsed,
    # as "dependencies" is not marked as dynamic.
    tmp_path = fake_project(
        files_with_declared_deps={
            ".subdir/requirements.txt": ["pandas"],
            ".subdir/requirements-test.txt": ["pylint >= 2.15.8"],
        },
        extra_file_contents={
            "pyproject.toml": """\
            [project]
            name = "MyLib"
            dynamic = ["optional-dependencies"]
            dependencies = ["django"]
            optional-dependencies = {"dev" = ["black"]}
            [tool.setuptools.dynamic]
            dependencies = { file = [".subdir/requirements.txt"] }
            optional-dependencies.test = { file = [".subdir/requirements-test.txt"] } """,
        },
    )
    expect = [
        "django",
        "pylint",
    ]
    settings = Settings(code=set(), deps={tmp_path})
    deps_sources = list(find_sources(settings, {DepsSource}))
    actual = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(actual, expect)


def test_find_and_parse_sources__project_with_setup_cfg__returns_list(fake_project):
    tmp_path = fake_project(
        files_with_declared_deps={
            "setup.cfg": ["pandas", "django"],  # install_requires
        },
        extra_file_contents={
            "setup.py": """\
                import setuptools

                if __name__ == "__main__":
                    setuptools.setup()
                """,
        },
    )
    expect = [
        "pandas",
        "django",
    ]
    settings = Settings(code=set(), deps={tmp_path})
    deps_sources = list(find_sources(settings, {DepsSource}))
    actual = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(actual, expect)


def test_find_and_parse_sources__project_with_setup_cfg_pyproject_requirements__returns_list(
    project_with_setup_with_cfg_pyproject_and_requirements,
):
    expect = [
        # from requirements.txt:
        "pandas",
        "click",
        # from setup.py:
        # from setup.cfg:
        "dependencyA",
        "dependencyB",
        # from subdir/dev-requirements.txt:
        "black",
        # from subdir/requirements.txt:
        "pandas",
        "tensorflow",
        # from subdir/requirements-docs.txt:
        "sphinx",
        # from pyproject.toml:
        "pandas",
        "pydantic",
        "pylint",
    ]
    settings = Settings(
        code=set(), deps={project_with_setup_with_cfg_pyproject_and_requirements}
    )
    deps_sources = list(find_sources(settings, {DepsSource}))
    actual = collect_dep_names(parse_sources(deps_sources))
    assert_unordered_equivalence(actual, expect)


@pytest.mark.parametrize(
    ("deps_file_content", "exp_deps"),
    [
        pytest.param(dedent(lines), exp, id=id_)
        for lines, exp, id_ in [
            (
                """
                FooProject >= 1.2 --global-option="--no-user-cfg" \\
                    --install-option="--prefix='/usr/local'" \\
                    --install-option="--no-compile" \\
                """,
                ["FooProject"],
                "original-use-case",
            ),
            (
                """
                FooProject --global-option="--no-user-cfg"
                MyProject
                """,
                ["FooProject", "MyProject"],
                "with-without",
            ),
            (
                """
                MyProject
                FooProject --global-option="--no-user-cfg"
                MyProject2
                """,
                ["MyProject", "FooProject", "MyProject2"],
                "without-with-without",
            ),
        ]
    ],
)
def test_parse_requirements_per_req_options(tmp_path, deps_file_content, exp_deps):
    # originally motivated by #114 (A dep can span multiple lines.)
    deps_path = tmp_path / "requirements.txt"
    deps_path.write_text(dedent(deps_file_content))
    obs_deps = collect_dep_names(parse_sources([validate_deps_source(deps_path)]))
    assert_unordered_equivalence(obs_deps, exp_deps)
