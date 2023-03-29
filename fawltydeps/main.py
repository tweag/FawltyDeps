"""Find undeclared and/or unused 3rd-party dependencies in your Python project.

Supports finding 3rd-party imports in Python scripts (*.py) and Jupyter
notebooks (*.ipynb).

Supports finding dependency declarations in *requirements*.txt (and .in) files,
pyproject.toml (following PEP 621 or Poetry conventions), setup.cfg, as well as
limited support for setup.py files with a single, simple setup() call and
minimal computation involved in setting the install_requires and extras_require
arguments.
"""

import json
import logging
import sys
from functools import partial, wraps
from operator import attrgetter
from typing import Callable, Dict, List, Optional, TextIO, TypeVar

from pydantic.json import custom_pydantic_encoder  # pylint: disable=no-name-in-module

from fawltydeps import extract_imports
from fawltydeps.check import calculate_undeclared, calculate_unused
from fawltydeps.cli import build_parser
from fawltydeps.extract_declared_dependencies import extract_declared_dependencies
from fawltydeps.packages import Package, resolve_dependencies
from fawltydeps.settings import Action, OutputFormat, Settings, print_toml_config
from fawltydeps.types import (
    DeclaredDependency,
    ParsedImport,
    UndeclaredDependency,
    UnparseablePathException,
    UnusedDependency,
)
from fawltydeps.utils import version

logger = logging.getLogger(__name__)

VERBOSE_PROMPT = "For a more verbose report re-run with the `--detailed` option."
UNUSED_DEPS_OUTPUT_PREFIX = "These dependencies appear to be unused (i.e. not imported)"


Instance = TypeVar("Instance")
T = TypeVar("T")


def calculated_once(method: Callable[[Instance], T]) -> Callable[[Instance], T]:
    """Emulate functools.cached_property for our simple use case.

    functools.cached_property does not exist in Python v3.7, so we emulate the
    simple things we need here:

    Each method that uses this decorator will store its return value in an
    instance attribute whose name is the method name prefixed with underscore.
    The first time the property is referenced, the method will be called, its
    return value stored in the corresponding instance attribute, and also
    returned to the caller. All subsequent references (as long as the stored
    value it not None) will return the instance attribute value directly,
    without calling the method.
    """

    @wraps(method)
    def wrapper(self: Instance) -> T:
        cached_attr = f"_{method.__name__}"
        cached_value: Optional[T] = getattr(self, cached_attr, None)
        if cached_value is not None:
            return cached_value
        calculated: T = method(self)
        setattr(self, cached_attr, calculated)
        return calculated

    return wrapper


class Analysis:  # pylint: disable=too-many-instance-attributes
    """Result from FawltyDeps analysis, to be presented to the user."""

    def __init__(self, settings: Settings, stdin: Optional[TextIO] = None):
        self.settings = settings
        self.stdin = stdin
        self.version = version()

        # The following members are calculated once, on-demand, by the
        # @property @calculated_once methods below:
        self._imports: Optional[List[ParsedImport]] = None
        self._declared_deps: Optional[List[DeclaredDependency]] = None
        self._resolved_deps: Optional[Dict[str, Package]] = None
        self._undeclared_deps: Optional[List[UndeclaredDependency]] = None
        self._unused_deps: Optional[List[UnusedDependency]] = None

    def is_enabled(self, *args: Action) -> bool:
        """Return True if any of the given actions are in self.settings."""
        return len(self.settings.actions.intersection(args)) > 0

    @property
    @calculated_once
    def imports(self) -> List[ParsedImport]:
        """The list of 3rd-party imports parsed from this project."""
        return list(extract_imports.parse_any_args(self.settings.code, self.stdin))

    @property
    @calculated_once
    def declared_deps(self) -> List[DeclaredDependency]:
        """The list of declared dependencies parsed from this project."""
        return list(
            extract_declared_dependencies(
                self.settings.deps, self.settings.deps_parser_choice
            )
        )

    @property
    @calculated_once
    def resolved_deps(self) -> Dict[str, Package]:
        """The resolved mapping of dependency names to provided import names."""
        return resolve_dependencies(
            (dep.name for dep in self.declared_deps),
            pyenv_path=self.settings.pyenv,
            install_deps=self.settings.install_deps,
        )

    @property
    @calculated_once
    def undeclared_deps(self) -> List[UndeclaredDependency]:
        """The import statements for which no declared dependency is found."""
        return calculate_undeclared(self.imports, self.resolved_deps, self.settings)

    @property
    @calculated_once
    def unused_deps(self) -> List[UnusedDependency]:
        """The declared dependencies that appear to not be in use."""
        return calculate_unused(
            self.imports, self.declared_deps, self.resolved_deps, self.settings
        )

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
        ret = cls(settings, stdin)

        # Compute only the properties needed to satisfy settings.actions:
        if ret.is_enabled(Action.LIST_IMPORTS):
            ret.imports  # pylint: disable=pointless-statement
        if ret.is_enabled(Action.LIST_DEPS):
            ret.declared_deps  # pylint: disable=pointless-statement
        if ret.is_enabled(Action.REPORT_UNDECLARED):
            ret.undeclared_deps  # pylint: disable=pointless-statement
        if ret.is_enabled(Action.REPORT_UNUSED):
            ret.unused_deps  # pylint: disable=pointless-statement

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
        json_dict = {
            "settings": self.settings,
            # Using properties with an underscore do not trigger computations.
            # They are populated only if the computations were already required
            # by settings.actions.
            "imports": self._imports,
            "declared_deps": self._declared_deps,
            "resolved_deps": self._resolved_deps,
            "undeclared_deps": self._undeclared_deps,
            "unused_deps": self._unused_deps,
            "version": self.version,
        }
        json.dump(json_dict, out, indent=2, default=encoder)

    def print_human_readable(self, out: TextIO, details: bool = True) -> None:
        """Print a human-readable rendering of this analysis to 'out'."""
        if self.is_enabled(Action.LIST_IMPORTS):
            if details:
                # Sort imports by source, then by name
                for imp in sorted(self.imports, key=attrgetter("source", "name")):
                    print(f"{imp.source}: {imp.name}", file=out)
            else:
                unique_imports = {i.name for i in self.imports}
                print("\n".join(sorted(unique_imports)), file=out)

        if self.is_enabled(Action.LIST_DEPS):
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
    parser = build_parser(description=__doc__)
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
