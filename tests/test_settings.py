"""Test how settings cascade/combine across command-line, config file, etc."""
import argparse
import logging
import random
import string
import sys
from dataclasses import dataclass, field
from itertools import chain, combinations, permutations, product
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import pytest
from hypothesis import given, strategies

from fawltydeps.main import build_parser
from fawltydeps.settings import DEFAULT_IGNORE_UNUSED, Action, OutputFormat, Settings
from fawltydeps.types import TomlData

if sys.version_info >= (3, 11):
    from tomllib import TOMLDecodeError
else:
    from tomli import TOMLDecodeError

try:  # import from Pydantic V2
    from pydantic.v1 import ValidationError
    from pydantic.v1.env_settings import SettingsError
except ModuleNotFoundError:
    from pydantic import ValidationError  # type: ignore[assignment]
    from pydantic.env_settings import SettingsError  # type: ignore[no-redef]

EXPECT_DEFAULTS = dict(
    actions={Action.REPORT_UNDECLARED, Action.REPORT_UNUSED},
    code={Path()},
    deps={Path()},
    pyenvs={Path()},
    custom_mapping=None,
    output_format=OutputFormat.HUMAN_SUMMARY,
    ignore_undeclared=set(),
    ignore_unused=DEFAULT_IGNORE_UNUSED,
    deps_parser_choice=None,
    install_deps=False,
    exclude={".*"},
    exclude_from=set(),
    verbosity=0,
    custom_mapping_file=set(),
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


@pytest.fixture()
def setup_env(monkeypatch):
    """Allow setup of fawltydeps_* env vars in a test case."""

    def _inner(**kwargs: str):
        for k, v in kwargs.items():
            monkeypatch.setenv(f"fawltydeps_{k}", v)

    return _inner


def paths_sets_equal(a: Set[str], b: Set[str]) -> bool:
    """Compare two sets of strings as if they were sets of paths."""
    return {Path(element) for element in a} == {Path(element) for element in b}


safe_string = strategies.text(alphabet=string.ascii_letters + string.digits, min_size=1)
nonempty_string_set = strategies.sets(safe_string, min_size=1)
four_different_string_groups = strategies.tuples(
    *([nonempty_string_set] * 4),
).filter(lambda ss: all(not paths_sets_equal(a, b) for a, b in combinations(ss, 2)))


@given(code_deps_pyenvs_base=four_different_string_groups)
def test_code_deps_pyenvs_and_base_unequal__raises_error(code_deps_pyenvs_base):
    code, deps, pyenvs, base = code_deps_pyenvs_base
    args = [*base, "--code", *code, "--deps", *deps, "--pyenv", *pyenvs]
    with pytest.raises(argparse.ArgumentError):
        run_build_settings(args)


path_options = {  # options (-> settings members) that interact with basepath
    "--code": "code",
    "--deps": "deps",
    "--pyenv": "pyenvs",
}

Item = TypeVar("Item")


def subsets(
    items: Set[Item],
    min_size: int = 0,
    max_size: int = sys.maxsize,
) -> Iterator[Set[Item]]:
    """Generate all subsets of the given set within the given size constraints.

    This is equivalent to the "power set" with a size filter applied.
    """
    max_size = min(max_size, len(items))
    for size in range(min_size, max_size + 1):
        for tpl in combinations(items, size):
            yield set(tpl)


@given(basepaths=nonempty_string_set, fillers=nonempty_string_set)
@pytest.mark.parametrize(
    ("filled", "unfilled"),
    [
        pytest.param(opts, path_options.keys() - opts, id="Passing " + ", ".join(opts))
        for opts in subsets(set(path_options.keys()), 1, len(path_options) - 1)
    ],
)
def test_path_option_overrides_base_path(basepaths, filled, unfilled, fillers):
    assert filled and unfilled and (unfilled | filled) == path_options.keys()
    args = list(basepaths)
    for option in filled:
        args += [option, *list(fillers)]
    settings = run_build_settings(args)
    for option in filled:
        assert getattr(settings, path_options[option]) == to_path_set(fillers)
    for option in unfilled:
        assert getattr(settings, path_options[option]) == to_path_set(basepaths)


@given(basepaths=nonempty_string_set)
def test_base_path_fills_path_options_when_other_path_settings_are_absent(basepaths):
    # Nothing else through CLI nor through config file
    settings = run_build_settings(cmdl=list(basepaths))
    expected = to_path_set(basepaths)
    assert all(getattr(settings, memb) == expected for memb in path_options.values())


@pytest.mark.parametrize(
    ("config_settings", "basepaths"),
    [
        pytest.param(conf_sett, base, id=test_name)
        for conf_sett, base, test_name in [
            (None, {"single-base"}, "empty-config"),
            ({"code": ["test-code"]}, {"base1", "base2"}, "only-code-set"),
            ({"deps": ["deps-test"]}, {"single-base"}, "only-deps-set"),
            ({"pyenvs": ["pyenvs-test"]}, {"single-base"}, "only-pyenvs-set"),
            (
                {"code": ["code-test"], "deps": ["test-deps"]},
                {"base1", "base2"},
                "code-and-deps-set",
            ),
            (
                {"code": ["code-test"], "deps": ["test-deps"], "pyenvs": ["abc"]},
                {"base1", "base2"},
                "all-three-set",
            ),
        ]
    ],
)
def test_base_path_overrides_config_file_for_all_path_options(
    config_settings,
    basepaths,
    setup_fawltydeps_config,
):
    config_file = (
        None if config_settings is None else setup_fawltydeps_config(config_settings)
    )

    settings = run_build_settings(cmdl=list(basepaths), config_file=config_file)
    expected = to_path_set(basepaths)
    assert all(getattr(settings, memb) == expected for memb in path_options.values())


OPTION_VALUES = {
    "code": {"a", "b", "c"},
    "deps": {"d", "e"},
    "ignore-undeclared": {"f", "g"},
    "ignore-unused": {"h", "i", "j"},
}


def multivalued_optargs_grid() -> Iterable[List[str]]:
    """Create shuffled argument list from OPTION_VALUES.

    Generate command-line option/argument combinations which mix order and
    number of multivalued parameters.
    """
    T = TypeVar("T")

    def subsequence_pairs(
        xs: Tuple[T, ...]
    ) -> Iterable[Tuple[Tuple[T, ...], Tuple[T, ...]]]:
        assert len(xs) >= 2  # noqa: PLR2004
        for i in range(1, len(xs)):
            yield xs[:i], xs[i:]

    option_partitions = [
        {pair for seq in permutations(items) for pair in subsequence_pairs(seq)}
        for items in OPTION_VALUES.values()
    ]

    opt_by_arg = {arg: opt for opt, argvals in OPTION_VALUES.items() for arg in argvals}

    for param_grid in set(product(*option_partitions)):
        xss = list(chain(*param_grid))
        random.shuffle(xss)
        yield list(chain(*[[f"--{opt_by_arg[xs[0]]}", *list(xs)] for xs in xss]))


@pytest.mark.parametrize("optargs", multivalued_optargs_grid())
def test_multivalued_options_are_aggregated_correctly(optargs):
    settings = run_build_settings(optargs)
    assert settings.code == to_path_set(OPTION_VALUES["code"])
    assert settings.deps == to_path_set(OPTION_VALUES["deps"])
    assert settings.ignore_undeclared == set(OPTION_VALUES["ignore-undeclared"])
    assert settings.ignore_unused == set(OPTION_VALUES["ignore-unused"])


@pytest.mark.parametrize(
    "optname",
    {act.dest for act in build_parser()._actions}  # noqa: SLF001
    & set(Settings.__fields__.keys()),
)
def test_settings_members_are_absent_from_namespace_if_not_provided_at_cli(optname):
    parsed_cli = build_parser().parse_args([])
    with pytest.raises(AttributeError):
        getattr(parsed_cli, optname)


@dataclass
class SettingsTestVector:
    """Test vectors for FawltyDeps Settings configuration."""

    id: str
    config: Optional[Union[str, TomlData]] = None
    env: Dict[str, str] = field(default_factory=dict)
    cmdline: Dict[str, Any] = field(default_factory=dict)
    expect: Union[Dict[str, Any], Type[Exception]] = field(
        default_factory=lambda: EXPECT_DEFAULTS
    )


settings_tests_samples = [
    SettingsTestVector("no_config_file__uses_defaults"),
    SettingsTestVector("empty_config_file__uses_defaults", config=""),
    SettingsTestVector("empty_config_file_section__uses_defaults", config={}),
    SettingsTestVector(
        "config_file_invalid_toml__raises_TOMLDecodeError",
        config="THIS IS BOGUS TOML",
        expect=TOMLDecodeError,
    ),
    SettingsTestVector(
        "config_file_unsupported_fields__raises_ValidationError",
        config=dict(code="my_code_dir", not_supported=123),  # unsupported directive
        expect=ValidationError,
    ),
    SettingsTestVector(
        "config_file_invalid_values__raises_ValidationError",
        config=dict(actions="list_imports"),  # actions is not a list
        expect=ValidationError,
    ),
    SettingsTestVector(
        "config_file__overrides_some_defaults",
        config=dict(actions=["list_deps"], deps=["my_requirements.txt"]),
        expect=make_settings_dict(
            actions={Action.LIST_DEPS}, deps={Path("my_requirements.txt")}
        ),
    ),
    SettingsTestVector(
        "config_file_with_mapping_file__overrides_some_defaults",
        config=dict(
            actions=["list_deps"],
            deps=["my_requirements.txt"],
            custom_mapping_file=["mapping.toml"],
        ),
        expect=make_settings_dict(
            actions={Action.LIST_DEPS},
            deps={Path("my_requirements.txt")},
            custom_mapping_file={Path("mapping.toml")},
        ),
    ),
    SettingsTestVector(
        "config_file_with_mapping__overrides_some_defaults",
        config=dict(
            actions=["list_deps"],
            deps=["my_requirements.txt"],
            custom_mapping={"package": ["foo", "bar"]},
        ),
        expect=make_settings_dict(
            actions={Action.LIST_DEPS},
            deps={Path("my_requirements.txt")},
            custom_mapping={"package": ["foo", "bar"]},
        ),
    ),
    SettingsTestVector(
        "config_file_with_mapping_and_cli__overrides_some_defaults",
        config=dict(
            actions=["list_deps"],
            deps=["my_requirements.txt"],
            custom_mapping={"package": ["foo", "bar"]},
        ),
        cmdline=dict(custom_mapping_file=["mapping.toml"]),
        expect=make_settings_dict(
            actions={Action.LIST_DEPS},
            deps={Path("my_requirements.txt")},
            custom_mapping={"package": ["foo", "bar"]},
            custom_mapping_file={Path("mapping.toml")},
        ),
    ),
    SettingsTestVector(
        "config_file_with_mapping_and_cli__cli_mapping_overrides_config",
        config=dict(custom_mapping_file=["foo.toml"]),
        cmdline=dict(custom_mapping_file=["mapping.toml"]),
        expect=make_settings_dict(
            custom_mapping_file={Path("mapping.toml")},
        ),
    ),
    SettingsTestVector(
        "config_file_with_pyenvs_and_cli__cli_pyenvs_overrides_config",
        config=dict(pyenvs=["foo", "bar"]),
        cmdline=dict(pyenvs=["baz", "xyzzy"]),
        expect=make_settings_dict(
            pyenvs={Path("baz"), Path("xyzzy")},
        ),
    ),
    SettingsTestVector(
        "env_var_with_wrong_type__raises_SettingsError",
        env=dict(actions="list_imports"),  # actions is not a list
        expect=SettingsError,
    ),
    SettingsTestVector(
        "env_var_with_invalid_value__raises_SettingsError",
        env=dict(ignore_unused='["foo", "missing_quote]'),  # cannot parse value
        expect=SettingsError,
    ),
    SettingsTestVector(
        "env_vars__overrides_some_defaults",
        env=dict(actions='["list_imports"]', ignore_unused='["foo", "bar"]'),
        expect=make_settings_dict(
            actions={Action.LIST_IMPORTS}, ignore_unused={"foo", "bar"}
        ),
    ),
    SettingsTestVector(
        "config_file_and_env_vars__overrides_separate_defaults",
        config=dict(code=["my_code_dir"], deps=["my_requirements.txt"]),
        env=dict(actions='["list_imports"]', ignore_unused='["foo", "bar"]'),
        expect=make_settings_dict(
            actions={Action.LIST_IMPORTS},
            code={Path("my_code_dir")},
            deps={Path("my_requirements.txt")},
            ignore_unused={"foo", "bar"},
        ),
    ),
    SettingsTestVector(
        "config_file_and_env_vars__env_overrides_file",
        config=dict(code="my_code_dir", deps=["my_requirements.txt"]),
        env=dict(actions='["list_imports"]', code='["<stdin>"]'),
        expect=make_settings_dict(
            actions={Action.LIST_IMPORTS},
            code={"<stdin>"},
            deps={Path("my_requirements.txt")},
        ),
    ),
    SettingsTestVector(
        "cmd_line_unsupported_field__is_ignored",
        cmdline=dict(unsupported=123),  # unsupported Settings field
    ),
    SettingsTestVector(
        "cmd_line_invalid_value__raises_ValidationError",
        cmdline=dict(actions="['wrong_action']"),  # invalid enum value
        expect=ValidationError,
    ),
    SettingsTestVector(
        "cmd_line_wrong_type__raises_ValidationError",
        cmdline=dict(actions="list_imports"),  # should be list/set, not str
        expect=ValidationError,
    ),
    SettingsTestVector(
        "cmd_line__overrides_some_defaults",
        cmdline=dict(actions={Action.LIST_IMPORTS}, ignore_unused={"foo", "bar"}),
        expect=make_settings_dict(
            actions={Action.LIST_IMPORTS}, ignore_unused={"foo", "bar"}
        ),
    ),
    SettingsTestVector(
        "cmd_line__overrides_config_file",
        config=dict(code="my_code_dir", deps=["my_requirements.txt"]),
        cmdline=dict(actions={Action.LIST_IMPORTS}, code={"<stdin>"}),
        expect=make_settings_dict(
            actions={Action.LIST_IMPORTS},
            code={"<stdin>"},
            deps={Path("my_requirements.txt")},
        ),
    ),
    SettingsTestVector(
        "cmd_line__verbose_minus_quiet__determines_verbosity",
        cmdline=dict(verbose=3, quiet=5),
        expect=make_settings_dict(verbosity=-2),
    ),
    SettingsTestVector(
        "cmd_line__verbose__overrides_env_verbosity",
        env=dict(verbosity="1"),
        cmdline=dict(verbose=2),
        expect=make_settings_dict(verbosity=2),
    ),
    SettingsTestVector(
        "cmd_line__no_verbose_no_quiet__uses_underlying_verbosity",
        config=dict(verbosity=-1),
        expect=make_settings_dict(verbosity=-1),
    ),
    SettingsTestVector(
        "cmd_line_env_var_and_config_file__cascades",
        config=dict(
            actions='["list_imports"]',
            code=["my_code_dir"],
            deps=["my_requirements.txt"],
            verbosity=1,
        ),
        env=dict(actions='["list_deps"]', code='["<stdin>"]'),
        cmdline=dict(code=["my_notebook.ipynb"], verbose=2, quiet=4),
        expect=make_settings_dict(
            actions={Action.LIST_DEPS},  # env overrides config file
            code={Path("my_notebook.ipynb")},  # cmd line overrides env + config file
            deps={Path("my_requirements.txt")},  # from config file
            verbosity=-2,  # calculated from cmd line, overrides config file
        ),
    ),
]


@pytest.mark.parametrize(
    "vector", [pytest.param(v, id=v.id) for v in settings_tests_samples]
)
def test_settings(vector, setup_fawltydeps_config, setup_env):
    config_file = (
        None if vector.config is None else setup_fawltydeps_config(vector.config)
    )
    setup_env(**vector.env)
    cmdline_args = argparse.Namespace(**vector.cmdline)
    if isinstance(vector.expect, dict):
        settings = Settings.config(config_file=config_file).create(cmdline_args)
        assert settings.dict() == vector.expect
    else:  # Assume we expect an exception
        with pytest.raises(vector.expect):
            Settings.config(config_file=config_file).create(cmdline_args)


def test_settings__instance__is_immutable():
    settings = Settings.config(config_file=None)()
    with pytest.raises(TypeError):
        settings.code = ["<stdin>"]
    assert settings.dict() == make_settings_dict()


def test_settings__missing_config_file__uses_defaults_and_warns(tmp_path, caplog):
    missing_file = tmp_path / "MISSING.toml"
    caplog.set_level(logging.INFO)
    settings = Settings.config(config_file=missing_file)()
    assert settings.dict() == make_settings_dict()
    assert "Failed to load configuration file:" in caplog.text
    missing_file_str = str(missing_file)
    # On Windows path escape sequences are doubled in repr()
    if sys.platform.startswith("win"):
        missing_file_str = repr(missing_file_str)
    assert missing_file_str in caplog.text


def to_path_set(ps: Iterable[str]) -> Set[Path]:
    return set(map(Path, ps))
