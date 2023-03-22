"""Find undeclared and/or unused 3rd-party dependencies in your Python project.

Supports finding 3rd-party imports in Python scripts (*.py) and Jupyter
notebooks (*.ipynb).

Supports finding dependency declarations in *requirements*.txt (and .in) files,
pyproject.toml (following PEP 621 or Poetry conventions), setup.cfg, as well as
limited support for setup.py files with a single, simple setup() call and
minimal computation involved in setting the install_requires and extras_require
arguments.
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from functools import partial
from operator import attrgetter
from pathlib import Path
from typing import Dict, List, Optional, TextIO, no_type_check

import importlib_metadata
from pydantic.json import custom_pydantic_encoder  # pylint: disable=no-name-in-module

from fawltydeps import extract_imports
from fawltydeps.check import calculate_undeclared, calculate_unused
from fawltydeps.extract_declared_dependencies import extract_declared_dependencies
from fawltydeps.packages import Package, resolve_dependencies
from fawltydeps.settings import (
    Action,
    OutputFormat,
    Settings,
    print_toml_config,
    setup_cmdline_parser,
)
from fawltydeps.types import (
    DeclaredDependency,
    ParsedImport,
    UndeclaredDependency,
    UnparseablePathException,
    UnusedDependency,
)

logger = logging.getLogger(__name__)

VERBOSE_PROMPT = "For a more verbose report re-run with the `--detailed` option."
UNUSED_DEPS_OUTPUT_PREFIX = "These dependencies appear to be unused (i.e. not imported)"


@no_type_check
def version() -> str:
    """Returns the version of fawltydeps."""

    # This function is extracted to allow annotation with `@no_type_check`.
    # Using `#type: ignore` on the line below leads to an
    # "unused type ignore comment" MyPy error in python's version 3.8 and
    # higher.
    return str(importlib_metadata.version("fawltydeps"))


@dataclass
class Analysis:
    """Result from FawltyDeps analysis, to be presented to the user."""

    settings: Settings
    imports: Optional[List[ParsedImport]] = None
    declared_deps: Optional[List[DeclaredDependency]] = None
    resolved_deps: Optional[Dict[str, Package]] = None
    undeclared_deps: Optional[List[UndeclaredDependency]] = None
    unused_deps: Optional[List[UnusedDependency]] = None
    version: str = version()

    def is_enabled(self, *args: Action) -> bool:
        """Return True if any of the given actions are in self.settings."""
        return len(self.settings.actions.intersection(args)) > 0

    @staticmethod
    def success_message(check_undeclared: bool, check_unused: bool) -> Optional[str]:
        """Returns the message to print when the analysis finds no errors."""
        checking = []
        if check_undeclared:
            checking.append("undeclared")
        if check_unused:
            checking.append("unused")
        if checking:
            return f"No {' or '.join(checking)} dependencies detected."
        return None

    @classmethod
    def create(cls, settings: Settings, stdin: Optional[TextIO] = None) -> "Analysis":
        """Exercise FawltyDeps' core logic according to the given settings.

        Perform the actions specified in 'settings.actions' and apply the other
        options in the 'settings' object.

        This is a high-level interface to the services offered by FawltyDeps.
        Although the main caller is the command-line interface defined below,
        this can also be called from other Python contexts without having to go
        via the command-line.
        """
        ret = cls(settings)
        if ret.is_enabled(
            Action.LIST_IMPORTS, Action.REPORT_UNDECLARED, Action.REPORT_UNUSED
        ):
            ret.imports = list(extract_imports.parse_any_args(settings.code, stdin))

        if ret.is_enabled(
            Action.LIST_DEPS, Action.REPORT_UNDECLARED, Action.REPORT_UNUSED
        ):
            ret.declared_deps = list(
                extract_declared_dependencies(
                    settings.deps, settings.deps_parser_choice
                )
            )

        if ret.is_enabled(Action.REPORT_UNDECLARED, Action.REPORT_UNUSED):
            assert ret.imports is not None  # convince Mypy that these cannot
            assert ret.declared_deps is not None  # be None at this time.
            ret.resolved_deps = resolve_dependencies(
                (dep.name for dep in ret.declared_deps),
                pyenv_path=settings.pyenv,
            )

        if ret.is_enabled(Action.REPORT_UNDECLARED):
            assert ret.imports is not None  # convince Mypy that these cannot
            assert ret.resolved_deps is not None  # be None at this time.
            ret.undeclared_deps = calculate_undeclared(
                ret.imports, ret.resolved_deps, settings
            )

        if ret.is_enabled(Action.REPORT_UNUSED):
            assert ret.imports is not None  # convince Mypy that these cannot
            assert ret.declared_deps is not None  # be None at this time.
            assert ret.resolved_deps is not None
            ret.unused_deps = calculate_unused(
                ret.imports, ret.declared_deps, ret.resolved_deps, settings
            )

        return ret

    def print_json(self, out: TextIO) -> None:
        """Print the JSON representation of this analysis to 'out'."""
        # The default pydantic_encoder uses list() to serialize set objects.
        # We need a stable serialization to JSON, so let's use sorted() instead.
        # However, not all elements that we store in a set are automatically
        # orderable (e.g. PathOrSpecial don't know how to order SpecialPath vs
        # Path), so order by string representation instead:
        set_sort = partial(sorted, key=str)
        encoder = partial(custom_pydantic_encoder, {frozenset: set_sort, set: set_sort})
        json.dump(self, out, indent=2, default=encoder)

    def print_human_readable(self, out: TextIO, details: bool = True) -> None:
        """Print a human-readable rendering of this analysis to 'out'."""
        if self.is_enabled(Action.LIST_IMPORTS):
            assert self.imports is not None  # sanity-check / convince Mypy
            if details:
                # Sort imports by source, then by name
                for imp in sorted(self.imports, key=attrgetter("source", "name")):
                    print(f"{imp.source}: {imp.name}", file=out)
            else:
                unique_imports = {i.name for i in self.imports}
                print("\n".join(sorted(unique_imports)), file=out)

        if self.is_enabled(Action.LIST_DEPS):
            assert self.declared_deps is not None  # sanity-check / convince Mypy
            if details:
                # Sort dependencies by location, then by name
                for dep in sorted(
                    set(self.declared_deps), key=attrgetter("source", "name")
                ):
                    print(f"{dep.source}: {dep.name}", file=out)
            else:
                print(
                    "\n".join(sorted(set(d.name for d in self.declared_deps))), file=out
                )

        if self.is_enabled(Action.REPORT_UNDECLARED) and self.undeclared_deps:
            print("\nThese imports appear to be undeclared dependencies:", file=out)
            for undeclared in self.undeclared_deps:
                print(f"- {undeclared.render(details)}", file=out)

        if self.is_enabled(Action.REPORT_UNUSED) and self.unused_deps:
            print(f"\n{UNUSED_DEPS_OUTPUT_PREFIX}:", file=out)
            for unused in sorted(self.unused_deps, key=lambda d: d.name):
                print(f"- {unused.render(details)}", file=out)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser, option_group = setup_cmdline_parser(description=__doc__)
    option_group.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"FawltyDeps v{version()}",
        help="Print the version number of FawltyDeps",
    )
    option_group.add_argument(
        "--config-file",
        type=Path,
        default=Path("./pyproject.toml"),
        help="Where to find FawltyDeps config (default: ./pyproject.toml)",
    )
    option_group.add_argument(
        "--generate-toml-config",
        action="store_true",
        default=False,
        help="Print a TOML config section with the current settings, and exit",
    )
    return parser


def assign_exit_code(analysis: Analysis) -> int:
    """
    Assign exit code based on the analysis results.

    Exit codes:
    0 - success, no problems found
    1 - an exception propagates (this should not happen)
    2 - command-line parsing error (generated in 'main')
    3 - undeclared dependencies found
    4 - unused dependencies found
    """
    if analysis.is_enabled(Action.REPORT_UNDECLARED) and analysis.undeclared_deps:
        return 3
    if analysis.is_enabled(Action.REPORT_UNUSED) and analysis.unused_deps:
        return 4

    return 0


def print_output(
    analysis: Analysis,
    exit_code: int,
    stdout: TextIO = sys.stdout,
) -> None:
    """Print the output of the given 'analysis' to 'stdout'."""
    success_message = Analysis.success_message(
        analysis.is_enabled(Action.REPORT_UNDECLARED),
        analysis.is_enabled(Action.REPORT_UNUSED),
    )

    if analysis.settings.output_format == OutputFormat.JSON:
        analysis.print_json(stdout)
    elif analysis.settings.output_format == OutputFormat.HUMAN_DETAILED:
        analysis.print_human_readable(sys.stdout, details=True)
        if exit_code == 0 and success_message:
            print(f"\n{success_message}", file=stdout)
    elif analysis.settings.output_format == OutputFormat.HUMAN_SUMMARY:
        analysis.print_human_readable(stdout, details=False)
        if exit_code == 0 and success_message:
            print(f"\n{success_message}", file=stdout)
        else:
            print(f"\n{VERBOSE_PROMPT}", file=stdout)
    else:
        raise NotImplementedError


def main(
    cmdline_args: Optional[List[str]] = None,  # defaults to sys.argv[1:]
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> int:
    """Command-line entry point."""
    parser = build_parser()
    args = parser.parse_args(cmdline_args)
    settings = Settings.config(config_file=args.config_file).create(args)

    logging.basicConfig(level=logging.WARNING - 10 * settings.verbosity)

    if args.generate_toml_config:
        print_toml_config(settings, stdout)
        return 0

    try:
        analysis = Analysis.create(settings, stdin)
    except UnparseablePathException as exc:
        return parser.error(exc.msg)  # exit code 2

    exit_code = assign_exit_code(analysis=analysis)
    print_output(analysis=analysis, exit_code=exit_code, stdout=stdout)

    return exit_code
