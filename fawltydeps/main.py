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
from functools import partial
from operator import attrgetter
from typing import BinaryIO, Dict, Iterator, List, Optional, Set, TextIO, Type

try:  # import from Pydantic V2
    from pydantic.v1.json import custom_pydantic_encoder
except ModuleNotFoundError:
    from pydantic.json import custom_pydantic_encoder  # type: ignore[no-redef]

from fawltydeps import extract_declared_dependencies, extract_imports
from fawltydeps.check import calculate_undeclared, calculate_unused
from fawltydeps.cli_parser import build_parser
from fawltydeps.packages import (
    BasePackageResolver,
    Package,
    resolve_dependencies,
    setup_resolvers,
)
from fawltydeps.settings import Action, OutputFormat, Settings, print_toml_config
from fawltydeps.traverse_project import find_sources
from fawltydeps.types import (
    CodeSource,
    DeclaredDependency,
    DepsSource,
    ParsedImport,
    PyEnvSource,
    Source,
    UndeclaredDependency,
    UnparseablePathException,
    UnresolvedDependenciesError,
    UnusedDependency,
)
from fawltydeps.utils import calculated_once, version

logger = logging.getLogger(__name__)

VERBOSE_PROMPT = "For a more verbose report re-run with the `--detailed` option."
UNUSED_DEPS_OUTPUT_PREFIX = "These dependencies appear to be unused (i.e. not imported)"


class Analysis:  # pylint: disable=too-many-instance-attributes
    """Result from FawltyDeps analysis, to be presented to the user.

    This collects the various data structures that are central to FawltyDeps'
    functionality. Depending on which actions are enabled settings.actions, we
    will _avoid_ calculating members in this class that are not needed (e.g.
    when the user passes --list-imports, we don't need to look for dependency
    declarations, nor do we need to calculate undeclared/unused dependencies).

    The implicit sequence/dependency between the members is as follows:
    - .sources (a set of CodeSource, DepsSource and/or PyEnvSource objects)
        reflect the result of traversing the project structure.
    - .imports contains the imports found by parsing the CodeSources.
    - .declared_deps contains the declared dependencies found by parsing the
        DepsSources.
    - .resolved_deps contains the mapping from .declared_deps to the Python
        package that expose the corresponding imports. This package is found
        within one of the PyEnvSources.
    - .undeclared_deps is calculated by finding the .imports that are not
        present in any of the .resolved_deps.
    - .unused_deps is the subset of .declared_deps whose corresponding packages
        only provide imports that are never actually imported (i.e. present in
        .imports).
    """

    def __init__(self, settings: Settings, stdin: Optional[BinaryIO] = None):
        self.settings = settings
        self.stdin = stdin
        self.version = version()

        # The following members are calculated once, on-demand, by the
        # @property @calculated_once methods below:
        self._sources: Optional[Set[Source]] = None
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
    def sources(self) -> Set[Source]:
        """The input sources (code, deps, pyenv) found in this project."""
        # What Source types are needed for which action?
        source_types: Dict[Action, Set[Type[Source]]] = {
            Action.LIST_SOURCES: {CodeSource, DepsSource, PyEnvSource},
            Action.LIST_IMPORTS: {CodeSource},
            Action.LIST_DEPS: {DepsSource},
            Action.REPORT_UNDECLARED: {CodeSource, DepsSource, PyEnvSource},
            Action.REPORT_UNUSED: {CodeSource, DepsSource, PyEnvSource},
        }
        return set(
            find_sources(
                self.settings,
                set.union(*[source_types[action] for action in self.settings.actions]),
            )
        )

    @property
    @calculated_once
    def imports(self) -> List[ParsedImport]:
        """The list of 3rd-party imports parsed from this project."""
        return list(
            extract_imports.parse_sources(
                (src for src in self.sources if isinstance(src, CodeSource)),
                self.stdin,
            )
        )

    @property
    @calculated_once
    def declared_deps(self) -> List[DeclaredDependency]:
        """The list of declared dependencies parsed from this project."""
        return list(
            extract_declared_dependencies.parse_sources(
                (src for src in self.sources if isinstance(src, DepsSource))
            )
        )

    @property
    @calculated_once
    def resolved_deps(self) -> Dict[str, Package]:
        """The resolved mapping of dependency names to provided import names."""
        return resolve_dependencies(
            (dep.name for dep in self.declared_deps),
            setup_resolvers(
                custom_mapping_files=self.settings.custom_mapping_file,
                custom_mapping=self.settings.custom_mapping,
                pyenv_srcs={
                    src for src in self.sources if isinstance(src, PyEnvSource)
                },
                install_deps=self.settings.install_deps,
            ),
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
    def create(cls, settings: Settings, stdin: Optional[BinaryIO] = None) -> "Analysis":
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
        if ret.is_enabled(Action.LIST_SOURCES):
            ret.sources  # pylint: disable=pointless-statement
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
        custom_type_encoders = {
            frozenset: partial(sorted, key=str),
            set: partial(sorted, key=str),
            type(BasePackageResolver): lambda klass: klass.__name__,
            type(Source): lambda klass: klass.__name__,
        }
        encoder = partial(custom_pydantic_encoder, custom_type_encoders)
        json_dict = {
            "settings": self.settings,
            # Using properties with an underscore do not trigger computations.
            # They are populated only if the computations were already required
            # by settings.actions.
            "sources": self._sources,
            "imports": self._imports,
            "declared_deps": self._declared_deps,
            "resolved_deps": self._resolved_deps,
            "undeclared_deps": self._undeclared_deps,
            "unused_deps": self._unused_deps,
            "version": self.version,
        }
        json.dump(json_dict, out, indent=2, default=encoder)

    def print_human_readable(self, out: TextIO, detailed: bool = True) -> None:
        """Print a human-readable rendering of this analysis to 'out'."""

        def render_sources() -> Iterator[str]:
            if detailed:
                # Sort sources by type, then by path
                source_types = [
                    (CodeSource, "Sources of Python code:"),
                    (DepsSource, "Sources of declared dependencies:"),
                    (PyEnvSource, "Python environments:"),
                ]
                for source_type, heading in source_types:
                    filtered = {s for s in self.sources if s.source_type is source_type}
                    if filtered:
                        yield "\n" + heading
                        yield from sorted([f"  {src.render(True)}" for src in filtered])
            else:
                yield from sorted({src.render(False) for src in self.sources})

        def render_imports() -> Iterator[str]:
            if detailed:
                # Sort imports by source, then by name
                for imp in sorted(self.imports, key=attrgetter("source", "name")):
                    yield f"{imp.source}: {imp.name}"
            else:
                unique_imports = {i.name for i in self.imports}
                yield from sorted(unique_imports)

        def render_declared_deps() -> Iterator[str]:
            if detailed:
                # Sort dependencies by source, then by name
                unique_deps = set(self.declared_deps)
                for dep in sorted(unique_deps, key=attrgetter("source", "name")):
                    yield f"{dep.source}: {dep.name}"
            else:
                yield from sorted(set(d.name for d in self.declared_deps))

        def render_undeclared() -> Iterator[str]:
            yield "\nThese imports appear to be undeclared dependencies:"
            for undeclared in self.undeclared_deps:
                yield f"- {undeclared.render(detailed)}"

        def render_unused() -> Iterator[str]:
            yield f"\n{UNUSED_DEPS_OUTPUT_PREFIX}:"
            for unused in sorted(self.unused_deps, key=lambda d: d.name):
                yield f"- {unused.render(detailed)}"

        def output(lines: Iterator[str]) -> None:
            for line in lines:
                print(line, file=out)

        if self.is_enabled(Action.LIST_SOURCES):
            output(render_sources())
        if self.is_enabled(Action.LIST_IMPORTS):
            output(render_imports())
        if self.is_enabled(Action.LIST_DEPS):
            output(render_declared_deps())
        if self.is_enabled(Action.REPORT_UNDECLARED) and self.undeclared_deps:
            output(render_undeclared())
        if self.is_enabled(Action.REPORT_UNUSED) and self.unused_deps:
            output(render_unused())

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
    5 - unresolved packages found error (generated in 'main')
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
        analysis.print_human_readable(stdout, detailed=True)
        if exit_code == 0 and success_message:
            print(f"\n{success_message}", file=stdout)
    elif analysis.settings.output_format == OutputFormat.HUMAN_SUMMARY:
        analysis.print_human_readable(stdout, detailed=False)
        if exit_code == 0 and success_message:
            print(f"\n{success_message}", file=stdout)
        else:
            print(f"\n{VERBOSE_PROMPT}", file=stdout)
    else:
        raise NotImplementedError


def main(
    cmdline_args: Optional[List[str]] = None,  # defaults to sys.argv[1:]
    stdin: BinaryIO = sys.stdin.buffer,
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
    except UnresolvedDependenciesError as exc:
        logger.error(
            "%s\nFawltyDeps is unable to find the above packages with the "
            "configured package resolvers. Consider using --pyenv if these "
            "packages are already installed somewhere, or --custom-mapping-file "
            "to take full control of the package-to-import-names mapping.",
            str(exc.msg),
        )
        return 5

    exit_code = assign_exit_code(analysis=analysis)
    print_output(analysis=analysis, exit_code=exit_code, stdout=stdout)

    return exit_code
