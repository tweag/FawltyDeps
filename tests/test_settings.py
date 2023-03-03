"""Test how settings cascade/combine across command-line, config file, etc."""
import argparse
import logging
import string
import sys
from pathlib import Path
from typing import List, Optional

import pytest
from hypothesis import given, strategies
from pydantic import ValidationError
from pydantic.env_settings import SettingsError  # pylint: disable=no-name-in-module

from fawltydeps.main import build_parser
from fawltydeps.settings import Action, OutputFormat, Settings

if sys.version_info >= (3, 11):
    from tomllib import TOMLDecodeError  # pylint: disable=no-member
else:
    from tomli import TOMLDecodeError

EXPECT_DEFAULTS = dict(
    actions={Action.REPORT_UNDECLARED, Action.REPORT_UNUSED},
    code=Path("."),
    deps=Path("."),
    output_format=OutputFormat.HUMAN_SUMMARY,
    ignore_undeclared=set(),
    ignore_unused=set(),
    deps_parser_choice=None,
    verbosity=0,
)


def run_build_settings(cmdl: List[str], config_file: Optional[Path] = None) -> Settings:
    """Combine the two relevant function calls to get a Settings."""
    parser = build_parser()
    args = parser.parse_args(cmdl)
    return Settings.config(config_file=config_file).create(args)


def make_settings_dict(**kwargs):
    """Create an expected version of Settings.dict(), with customizations.

    Return a copy of EXPECT_DEFAULTS, with the given customizations applied.
    """
    ret = EXPECT_DEFAULTS.copy()
    ret.update(kwargs)
    return ret


@pytest.fixture
def setup_env(monkeypatch):
    """Allow setup of fawltydeps_* env vars in a test case"""

    def _inner(**kwargs: str):
        for k, v in kwargs.items():
            monkeypatch.setenv(f"fawltydeps_{k}", v)

    return _inner


safe_string = strategies.text(alphabet=string.ascii_letters + string.digits, min_size=1)
three_different_strings = strategies.tuples(
    safe_string, safe_string, safe_string
).filter(lambda ss: len(ss) == len(set(ss)))


@given(code_deps_base=three_different_strings)
def test_code_deps_and_base_unequal__raises_error(code_deps_base):
    code, deps, base = code_deps_base
    with pytest.raises(argparse.ArgumentError):
        run_build_settings([f"--code={code}", f"--deps={deps}", base])


@given(basepath=safe_string)
@pytest.mark.parametrize(["filled", "unfilled"], [("code", "deps"), ("deps", "code")])
def test_base_path_respects_path_already_filled_via_cli(basepath, filled, unfilled):
    filler = "This_is_a_filler"
    settings = run_build_settings([f"--{filled}={filler}", basepath])
    assert getattr(settings, filled) == Path(filler)
    assert getattr(settings, unfilled) == Path(basepath)


@given(basepath=safe_string)
def test_base_path_fills_code_and_deps_when_other_path_settings_are_absent(basepath):
    # Nothing else through CLI nor through config file
    settings = run_build_settings([basepath])
    assert settings.code == Path(basepath)
    assert settings.deps == Path(basepath)


@pytest.mark.parametrize(
    "config_settings",
    [
        pytest.param(conf_sett, id=test_name)
        for conf_sett, test_name in [
            (None, "empty-config"),
            (dict(code="test-code"), "only-code-set"),
            (dict(deps="deps-test"), "only-deps-set"),
            (dict(code="code-test", deps="test-deps"), "code-and-deps-set"),
        ]
    ],
)
def test_base_path_overrides_config_file_code_and_deps(
    config_settings, setup_fawltydeps_config
):
    config_file = (
        None if config_settings is None else setup_fawltydeps_config(config_settings)
    )
    basepath = Path("my-temp-basepath")
    settings = run_build_settings(cmdl=[str(basepath)], config_file=config_file)
    assert settings.code == basepath
    assert settings.deps == basepath


@pytest.mark.parametrize(
    "config_settings,env_settings,cmdline_settings,expect",
    [
        pytest.param(
            None,  # config file disabled
            {},
            {},
            EXPECT_DEFAULTS,
            id="no_config_file__uses_defaults",
        ),
        pytest.param(
            "",  # empty pyproject.toml
            {},
            {},
            EXPECT_DEFAULTS,
            id="empty_config_file__uses_defaults",
        ),
        pytest.param(
            {},  # pyproject.toml with empty [tool.fawltydeps] section
            {},
            {},
            EXPECT_DEFAULTS,
            id="empty_config_file_section__uses_defaults",
        ),
        pytest.param(
            "THIS IS BOGUS TOML",  # pyproject.toml with invalid TOML
            {},
            {},
            TOMLDecodeError,
            id="config_file_invalid_toml__raises_TOMLDecodeError",
        ),
        pytest.param(
            dict(code="my_code_dir", not_supported=123),  # unsupported directive
            {},
            {},
            ValidationError,
            id="config_file_unsupported_fields__raises_ValidationError",
        ),
        pytest.param(
            dict(actions="list_imports"),  # actions is not a list
            {},
            {},
            ValidationError,
            id="config_file_invalid_values__raises_ValidationError",
        ),
        pytest.param(
            dict(actions=["list_deps"], deps="my_requirements.txt"),
            {},
            {},
            make_settings_dict(
                actions={Action.LIST_DEPS}, deps=Path("my_requirements.txt")
            ),
            id="config_file__overrides_some_defaults",
        ),
        pytest.param(
            None,
            dict(actions="list_imports"),  # actions is not a list
            {},
            SettingsError,
            id="env_var_with_wrong_type__raises_SettingsError",
        ),
        pytest.param(
            None,
            dict(ignore_unused='["foo", "missing_quote]'),  # cannot parse value
            {},
            SettingsError,
            id="env_var_with_invalid_value__raises_SettingsError",
        ),
        pytest.param(
            None,
            dict(actions='["list_imports"]', ignore_unused='["foo", "bar"]'),
            {},
            make_settings_dict(
                actions={Action.LIST_IMPORTS}, ignore_unused={"foo", "bar"}
            ),
            id="env_vars__overrides_some_defaults",
        ),
        pytest.param(
            dict(code="my_code_dir", deps="my_requirements.txt"),
            dict(actions='["list_imports"]', ignore_unused='["foo", "bar"]'),
            {},
            make_settings_dict(
                actions={Action.LIST_IMPORTS},
                code=Path("my_code_dir"),
                deps=Path("my_requirements.txt"),
                ignore_unused={"foo", "bar"},
            ),
            id="config_file_and_env_vars__overrides_separate_defaults",
        ),
        pytest.param(
            dict(code="my_code_dir", deps="my_requirements.txt"),
            dict(actions='["list_imports"]', code="<stdin>"),
            {},
            make_settings_dict(
                actions={Action.LIST_IMPORTS},
                code="<stdin>",
                deps=Path("my_requirements.txt"),
            ),
            id="config_file_and_env_vars__env_overrides_file",
        ),
        pytest.param(
            None,
            {},
            dict(unsupported=123),  # unsupported Settings field
            EXPECT_DEFAULTS,
            id="cmd_line_unsupported_field__is_ignored",
        ),
        pytest.param(
            None,
            {},
            dict(actions="['wrong_action']"),  # invalid enum value
            ValidationError,
            id="cmd_line_invalid_value__raises_ValidationError",
        ),
        pytest.param(
            None,
            {},
            dict(actions="list_imports"),  # should be list/set, not str
            ValidationError,
            id="cmd_line_wrong_type__raises_ValidationError",
        ),
        pytest.param(
            None,
            {},
            dict(actions={Action.LIST_IMPORTS}, ignore_unused={"foo", "bar"}),
            make_settings_dict(
                actions={Action.LIST_IMPORTS}, ignore_unused={"foo", "bar"}
            ),
            id="cmd_line__overrides_some_defaults",
        ),
        pytest.param(
            dict(code="my_code_dir", deps="my_requirements.txt"),
            {},
            dict(actions={Action.LIST_IMPORTS}, code="<stdin>"),
            make_settings_dict(
                actions={Action.LIST_IMPORTS},
                code="<stdin>",
                deps=Path("my_requirements.txt"),
            ),
            id="cmd_line__overrides_config_file",
        ),
        pytest.param(
            None,
            {},
            dict(verbose=3, quiet=5),
            make_settings_dict(verbosity=-2),
            id="cmd_line__verbose_minus_quiet__determines_verbosity",
        ),
        pytest.param(
            None,
            dict(verbosity="1"),
            dict(verbose=2),
            make_settings_dict(verbosity=2),
            id="cmd_line__verbose__overrides_env_verbosity",
        ),
        pytest.param(
            dict(verbosity=-1),
            {},
            {},
            make_settings_dict(verbosity=-1),
            id="cmd_line__no_verbose_no_quiet__uses_underlying_verbosity",
        ),
        pytest.param(
            dict(
                actions='["list_imports"]',
                code="my_code_dir",
                deps="my_requirements.txt",
                verbosity=1,
            ),
            dict(actions='["list_deps"]', code="<stdin>"),
            dict(code="my_notebook.ipynb", verbose=2, quiet=4),
            make_settings_dict(
                actions={Action.LIST_DEPS},  # env overrides config file
                code=Path("my_notebook.ipynb"),  # cmd line overrides env + config file
                deps=Path("my_requirements.txt"),  # from config file
                verbosity=-2,  # calculated from cmd line, overrides config file
            ),
            id="cmd_line_env_var_and_config_file__cascades",
        ),
    ],
)
def test_settings(
    config_settings,
    env_settings,
    cmdline_settings,
    expect,
    setup_fawltydeps_config,
    setup_env,
):  # pylint: disable=too-many-arguments
    if config_settings is None:
        config_file = None
    else:
        config_file = setup_fawltydeps_config(config_settings)
    setup_env(**env_settings)
    cmdline_args = argparse.Namespace(**cmdline_settings)
    if isinstance(expect, dict):
        settings = Settings.config(config_file=config_file).create(cmdline_args)
        assert settings.dict() == expect
    else:  # Assume we expect an exception
        with pytest.raises(expect):
            Settings.config(config_file=config_file).create(cmdline_args)


def test_settings__instance__is_immutable():
    settings = Settings.config(config_file=None)()
    with pytest.raises(TypeError):
        settings.code = "<stdin>"
    assert settings.dict() == make_settings_dict()


def test_settings__missing_config_file__uses_defaults_and_warns(tmp_path, caplog):
    missing_file = tmp_path / "MISSING.toml"
    caplog.set_level(logging.INFO)
    settings = Settings.config(config_file=missing_file)()
    assert settings.dict() == make_settings_dict()
    assert "Failed to load configuration file:" in caplog.text
    assert str(missing_file) in caplog.text
