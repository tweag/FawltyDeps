"""Find undeclared and/or unused 3rd-party dependencies in your Python project.

* Supported files for Python code containing third-party imports:
  * Python scripts with filenames that end in `.py`
  * Jupyter notebooks with filenames that end in `.ipynb`

* Supported files/formats for dependency declarations:
  * `*requirements*.txt` and `*requirements*.in`
  * `pyproject.toml` (following PEP 621 or Poetry conventions)
  * `setup.py` (only limited support for simple files with a single `setup()`
    call and no computation involved for setting the `install_requires` and
    `extras_require` arguments)
  * `setup.cfg`
"""

import json
import logging
import sys
from dataclasses import dataclass
from functools import partial
from operator import attrgetter
from pathlib import Path
from typing import List, Optional, TextIO, no_type_check

from pydantic.json import custom_pydantic_encoder  # pylint: disable=no-name-in-module

from fawltydeps import extract_imports
from fawltydeps.check import compare_imports_to_dependencies
from fawltydeps.extract_declared_dependencies import extract_declared_dependencies
from fawltydeps.settings import Action, OutputFormat, Settings, setup_cmdline_parser
from fawltydeps.types import (
    DeclaredDependency,
    ParsedImport,
    UndeclaredDependency,
    UnparseablePathException,
    UnusedDependency,
)

if sys.version_info >= (3, 8):
    import importlib.metadata as importlib_metadata
else:
    import importlib_metadata


logger = logging.getLogger(__name__)

VERBOSE_PROMPT = "For a more verbose report re-run with the `--detailed` option."


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
    undeclared_deps: Optional[List[UndeclaredDependency]] = None
    unused_deps: Optional[List[UnusedDependency]] = None
    version: str = version()

    def is_enabled(self, *args: Action) -> bool:
        """Return True if any of the given actions are in self.settings."""
        return len(self.settings.actions.intersection(args)) > 0

    @classmethod
    def create(cls, settings: Settings) -> "Analysis":
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
            ret.imports = list(extract_imports.parse_any_arg(settings.code))

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
            ret.undeclared_deps, ret.unused_deps = compare_imports_to_dependencies(
                imports=ret.imports,
                dependencies=ret.declared_deps,
                settings=settings,
            )

        return ret

    def print_json(self, out: TextIO) -> None:
        """Print the JSON representation of this analysis to 'out'."""
        # The default pydantic_encoder uses list() to serialize set objects.
        # Use sorted() instead, to ensure stable serialization to JSON.
        # This requires that all our sets contain orderable elements!
        encoder = partial(custom_pydantic_encoder, {frozenset: sorted, set: sorted})
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
                for dep in sorted(self.declared_deps, key=attrgetter("source", "name")):
                    print(f"{dep.source}: {dep.name}", file=out)
            else:
                unique_dependencies = {i.name for i in self.declared_deps}
                print("\n".join(sorted(unique_dependencies)), file=out)

        if self.is_enabled(Action.REPORT_UNDECLARED) and self.undeclared_deps:
            print("These imports appear to be undeclared dependencies:", file=out)
            for undeclared in self.undeclared_deps:
                print(f"- {undeclared.render(details)}", file=out)

        if self.is_enabled(Action.REPORT_UNUSED) and self.unused_deps:
            print(
                "These dependencies appear to be unused (i.e. not imported):", file=out
            )
            for unused in self.unused_deps:
                print(f"- {unused.render(details)}", file=out)


def main() -> int:
    """Command-line entry point."""
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

    args = parser.parse_args()
    settings = Settings.config(config_file=args.config_file).create(args)

    logging.basicConfig(level=logging.WARNING - 10 * settings.verbosity)

    try:
        analysis = Analysis.create(settings)
    except UnparseablePathException as exc:
        return parser.error(exc.msg)  # exit code 2

    if settings.output_format == OutputFormat.JSON:
        analysis.print_json(sys.stdout)
    elif settings.output_format == OutputFormat.HUMAN_DETAILED:
        analysis.print_human_readable(sys.stdout, details=True)
    elif settings.output_format == OutputFormat.HUMAN_SUMMARY:
        analysis.print_human_readable(sys.stdout, details=False)
        print(f"\n{VERBOSE_PROMPT}")
    else:
        raise NotImplementedError

    # Exit codes:
    # 0 - success, no problems found
    # 1 - an exception propagates (this should not happen)
    # 2 - command-line parsing error (see above)
    # 3 - undeclared dependencies found
    # 4 - unused dependencies found
    if analysis.is_enabled(Action.REPORT_UNDECLARED) and analysis.undeclared_deps:
        return 3
    if analysis.is_enabled(Action.REPORT_UNUSED) and analysis.unused_deps:
        return 4
    return 0
