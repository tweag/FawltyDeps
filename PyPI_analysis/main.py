import json
import logging
import sys
from collections import Counter
from functools import partial
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, TextIO, Type

try:  # import from Pydantic V2
    from pydantic.v1.json import custom_pydantic_encoder
except ModuleNotFoundError:
    from pydantic.json import custom_pydantic_encoder  # type: ignore[no-redef]

from fawltydeps.packages import BasePackageResolver
from fawltydeps.settings import Action, OutputFormat, Settings
from fawltydeps.traverse_project import find_sources
from fawltydeps.types import (
    CodeSource,
    DepsSource,
    ParsedImport,
    PyEnvSource,
    Source,
    UnparseablePathException,
    UnresolvedDependenciesError,
)
from fawltydeps.utils import calculated_once, version
from PyPI_analysis import detect_imports
from PyPI_analysis.cli_parser import build_parser

logger = logging.getLogger(__name__)

VERBOSE_PROMPT = "For a more verbose report re-run with the `--detailed` option."


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
    """

    def __init__(
        self, settings: Settings, project_name: str, stdin: Optional[TextIO] = None
    ):
        self.settings = settings
        self.stdin = stdin
        self.version = version()
        self.project_name = project_name

        # The following members are calculated once, on-demand, by the
        # @property @calculated_once methods below:
        self._sources: Optional[Set[Source]] = None
        self._imports: Optional[List[Dict[str, ParsedImport]]] = None
        self._code_dirs: Optional[Dict[Path, int]] = None

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
        }
        return set(
            find_sources(
                self.settings,
                set.union(
                    *[
                        source_types[action]
                        for action in {Action.LIST_IMPORTS, Action.LIST_SOURCES}
                    ]
                ),
            )
        )

    @property
    @calculated_once
    def imports(self) -> List[ParsedImport]:
        """The list of 3rd-party imports parsed from this project."""
        return list(
            detect_imports.parse_sources(
                (src for src in self.sources if isinstance(src, CodeSource)),
                self.stdin,
            )
        )

    @property
    @calculated_once
    def code_dirs(self) -> Optional[Dict[Path, int]]:
        """The directory that contains the main code"""
        code_paths = [
            src.path
            for src in self.sources
            if isinstance(src, CodeSource)
            and len(src.path.parts) > 1
            and "test" not in src.path.parts[0]
            and "example" not in src.path.parts[0]
            and "test" not in src.path.name
        ]
        directories = [path.parts[0] for path in code_paths]
        directory_counts = Counter(directories)
        if directory_counts:
            return dict(directory_counts)

    @classmethod
    def create(
        cls,
        settings: Settings,
        project_name: str,
        stdin: Optional[TextIO] = None,
    ) -> "Analysis":
        """Exercise FawltyDeps' core logic according to the given settings.

        Perform the actions specified in 'settings.actions' and apply the other
        options in the 'settings' object.

        This is a high-level interface to the services offered by FawltyDeps.
        Although the main caller is the command-line interface defined below,
        this can also be called from other Python contexts without having to go
        via the command-line.
        """
        ret = cls(settings, project_name, stdin)

        ret.sources
        ret.imports
        ret.code_dirs

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
            # Using properties with an underscore do not trigger computations.
            # They are populated only if the computations were already required
            # by settings.actions.
            "project_name": self.project_name,
            "code_dirs": self.code_dirs,
            "deps_file": {src for src in self._sources if isinstance(src, DepsSource)},
            "imports": self._imports,
            "fawltydeps_version": self.version,
        }
        json.dump(json_dict, out, indent=2, default=encoder)

    def print_human_readable(self, out: TextIO, detailed: bool = True) -> None:
        """Print a human-readable rendering of this analysis to 'out'."""

        def render_code_directory() -> Iterator[str]:
            if detailed:
                yield "Code directories: "
                if self.code_dirs:
                    for code_dir, count in self.code_dirs.items():
                        yield f"  {code_dir}: {count} Python files"
                else:
                    yield "  There is no main code directory found under the current directory."
            else:
                if self.code_dirs:
                    for code_dir, _count in self.code_dirs.items():
                        yield code_dir

        def render_dep_files() -> Iterator[str]:
            if detailed:
                yield "\nDependency declaration files:"
                dep_files = sorted(
                    {
                        f"  {src.parser_choice}: {src.render(True)}"
                        for src in self.sources
                        if isinstance(src, DepsSource)
                    }
                )
                if dep_files:
                    yield from dep_files
                else:
                    yield "  There is no dependency declaration file found."
            else:
                yield from sorted(
                    {
                        f"{src.parser_choice}: {src.render(False)}"
                        for src in self.sources
                        if isinstance(src, DepsSource)
                    }
                )

        def render_imports() -> Iterator[str]:
            if detailed:
                yield "\n" + "Patterns of imports:"
                if self.imports:
                    for imp in self.imports:
                        yield f"  {list(imp.keys())[0]}: {imp[list(imp.keys())[0]].source}: {imp[list(imp.keys())[0]].name}"
                else:
                    yield "  There is no import pattern found."
            else:
                unique_imports = {
                    list(imp.keys())[0] + ": " + imp[list(imp.keys())[0]].name
                    for imp in self.imports
                }
                yield from sorted(unique_imports)

        def output(lines: Iterator[str]) -> None:
            for line in lines:
                print(line, file=out)

        output(render_code_directory())
        output(render_dep_files())
        output(render_imports())

    @staticmethod
    def success_message(check_undeclared: bool, check_unused: bool) -> Optional[str]:
        """Returns the message to print when the analysis finds no errors."""
        return "No conditional or alternative imports detected."


def assign_exit_code(analysis: Analysis) -> int:
    """
    Assign exit code based on the analysis results.

    Exit codes:
    0 - success, no problems found
    1 - an exception propagates (this should not happen)
    2 - command-line parsing error (generated in 'main')
    5 - unresolved packages found error (generated in 'main')
    """

    return 0


def print_output(
    analysis: Analysis,
    stdout: TextIO = sys.stdout,
) -> None:
    """Print the output of the given 'analysis' to 'stdout'."""

    if analysis.settings.output_format == OutputFormat.JSON:
        analysis.print_json(stdout)
    elif analysis.settings.output_format == OutputFormat.HUMAN_DETAILED:
        analysis.print_human_readable(stdout, detailed=True)
    elif analysis.settings.output_format == OutputFormat.HUMAN_SUMMARY:
        analysis.print_human_readable(stdout, detailed=False)
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
    settings = Settings.config().create(args)

    logging.basicConfig(level=logging.WARNING - 10 * settings.verbosity)

    try:
        analysis = Analysis.create(settings, args.project_name, stdin)
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
    print_output(analysis=analysis, stdout=stdout)

    return exit_code
