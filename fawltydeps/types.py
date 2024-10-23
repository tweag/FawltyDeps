"""Common types used across FawltyDeps."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from functools import cached_property, total_ordering
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, Type, Union

from fawltydeps.utils import hide_dataclass_fields

SpecialPath = Literal["<stdin>"]
PathOrSpecial = Union[SpecialPath, Path]
TomlData = Dict[str, Any]  # type: ignore[misc]
CustomMapping = Dict[str, List[str]]


class UnparseablePathError(Exception):
    """Exception type when alleged path (deps or code) can't be parsed."""

    def __init__(self, ctx: str, path: Path):
        self.msg = f"{ctx}: {path}"


class UnresolvedDependenciesError(Exception):
    """Exception type when not all dependencies were are resolved."""

    def __init__(self, names: Set[str]):
        self.msg = f"Unresolved dependencies: {', '.join(sorted(names))}"


class ParserChoice(Enum):
    """Enumerate the choices of dependency declaration parsers."""

    REQUIREMENTS_TXT = "requirements.txt"
    SETUP_PY = "setup.py"
    SETUP_CFG = "setup.cfg"
    PYPROJECT_TOML = "pyproject.toml"
    PIXI_TOML = "pixi.toml"
    ENVIRONMENT_YML = "environment.yml"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, eq=True, order=True)
class Source(ABC):
    """Base class for some source of input to FawltyDeps.

    This exists to inject the class name of the subclass into our JSON output.
    """

    source_type: Type[Source] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_type", self.__class__)

    @abstractmethod
    def render(self, *, detailed: bool) -> str:
        """Return a human-readable string representation of this source."""
        raise NotImplementedError


@dataclass(frozen=True, eq=True, order=True)
class CodeSource(Source):
    """A Python code source to be parsed for import statements.

    .path points to the .py or .ipynb file containing Python code, alternatively
        it points to the "<stdin>" special case which means Python code will be
        read from standard input.
    .base_dir is an optional directory that contains modules/packages that
        should be considered _first_-party (i.e. _not_ third-path dependencies)
        when imported from the code in .path. More details at
        https://pycqa.github.io/isort/docs/configuration/options.html#src-paths
    """

    path: PathOrSpecial
    base_dir: Optional[Path] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.path != "<stdin>":
            assert isinstance(self.path, Path)  # noqa: S101, sanity check
            if not self.path.is_file():
                raise UnparseablePathError(
                    ctx="Code path to parse is neither dir nor file",
                    path=self.path,
                )
            if self.path.suffix not in {".py", ".ipynb"}:
                raise UnparseablePathError(
                    ctx="Supported formats are .py and .ipynb; Cannot parse code",
                    path=self.path,
                )

    def render(self, *, detailed: bool) -> str:
        """Return a human-readable string representation of this source."""
        if detailed and self.base_dir is not None:
            return f"{self.path} (using {self.base_dir} as base for 1st-party imports)"
        return f"{self.path}"


@dataclass(frozen=True, eq=True, order=True)
class DepsSource(Source):
    """A source to be parsed for declared dependencies.

    Also include which declared dependencies parser we have chosen to use for
    this file.

    .path points to the file containing dependency declarations.
    .parser_choice selects the parser/format to be used for extracting
        dependency declarations from .path. If this is not passed in explicitly
        (via Settings.deps_parser_choice) it will be automatically determined
        from looking at .path's filename (see first_applicable_parser() in
        extract_deps/__init__.py).
    """

    path: Path
    parser_choice: ParserChoice

    def __post_init__(self) -> None:
        super().__post_init__()
        assert self.path.is_file()  # noqa: S101, sanity check

    def render(self, *, detailed: bool) -> str:
        """Return a human-readable string representation of this source."""
        if detailed:
            return f"{self.path} (parsed as a {self.parser_choice} file)"
        return f"{self.path}"


@dataclass(frozen=True, eq=True, order=True)
class PyEnvSource(Source):
    """A source to be used for looking up installed Python packages.

    .path points to a directory that directly contains Python packages, e.g. the
        lib/pythonX.Y/site-packages directory in a system-wide Python
        installation (under /usr, /usr/local, or similar), in a virtualenv, in
        a poetry2nix environment, or a similar mechanism that uses this layout.
        Alternatively, it can be a __pypackages__/X.Y/lib directory within a
        project that uses PEP582.
    """

    path: Path

    def __post_init__(self) -> None:
        super().__post_init__()
        assert self.path.is_dir()  # noqa: S101, sanity check

        # Support virtualenvs and system-wide installs on Windows
        if sys.platform.startswith("win"):
            if (
                self.path.match(str(Path("Lib", "site-packages")))
                and (self.path.parent.parent / "Scripts" / "python.exe").is_file()
            ):
                return  # also ok
        # Support vitualenvs, poetry2nix envs, system-wide installs, etc. on POSIX
        else:
            python_exe = self.path.parent.parent.parent / "bin/python"
            if self.path.match("lib/python?.*/site-packages") and (
                python_exe.is_file() or python_exe.is_symlink()
            ):
                return  # all ok

        # Support projects using __pypackages__ from PEP582:
        if self.path.match("__pypackages__/?.*/lib"):
            return  # also ok

        raise ValueError(f"{self.path} is not a valid dir for Python packages!")

    def render(self, *, detailed: bool) -> str:
        """Return a human-readable string representation of this source."""
        if detailed:
            return f"{self.path} (as a source of Python packages)"
        return f"{self.path}"


@total_ordering
@dataclass(frozen=True)
class Location:
    """Reference to a source location, e.g. a file, a line within a file, etc.

    This is deliberately kept flexible, and the intention is for instances to
    be associated with data that originates from some input file (or even
    something read from a non-file like stdin), and carry as much or as little
    information as is appropriate about the _source_ of the associated data.

    Examples include referring to:
     - a specific line (+ column?) in a file of Python source code,
     - a line number in anonymous Python code read from stdin,
     - a file of dependency information (e.g. pyproject.toml) where a specific
       line number is not available (for any reason),
     - a specific cell in a Jupyter notebook.

    Instances have a string representation that reflect the level of detail
    provided, and they are sortable.
    """

    path: PathOrSpecial
    cellno: Optional[int] = None
    lineno: Optional[int] = None

    def __post_init__(self) -> None:
        """Do magic to hide unset/None members from JSON representation."""
        unset = [attr for attr, value in asdict(self).items() if value is None]
        hide_dataclass_fields(self, *unset)

    # It would be ideal to use the automatic __eq__, __lt__, etc. methods that
    # @dataclass can provide for us, thus making Location objects automatically
    # orderable/sortable. However, the automatic implementations end up directly
    # comparing tuples of our members, which fails when some of those members
    # are None, with errors like e.g.: TypeError: '<' not supported between
    # instances of 'PosixPath' and 'NoneType'.
    # Instead, we must implement our own. Do so based on a comparable/sortable
    # tuple created on demand and cached inside the instance:

    @cached_property
    def _sort_key(self) -> Tuple[str, int, int]:
        """Return a sortable key that uniquely reflects this instance.

        This is used to compare Location objects, and determine how they sort
        relative to each other. The following must hold:
        - All instance details are captured: equal sort key => equal instance
        - Member order matters: sort by path, then cellno, then lineno
        - Unspecified members sort together, and separate from specified members
        - Paths sort alphabetically, the other members sort numerically
        """
        return (
            repr(self.path),
            -1 if self.cellno is None else self.cellno,
            -1 if self.lineno is None else self.lineno,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Location):
            return NotImplemented
        return self._sort_key == other._sort_key

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Location):
            return NotImplemented
        return self._sort_key < other._sort_key

    def __hash__(self) -> int:
        return hash(self._sort_key)

    def __str__(self) -> str:
        ret = str(self.path)
        if self.cellno is not None:
            ret += f"[{self.cellno}]"
        if self.lineno is not None:
            ret += f":{self.lineno}"
        return ret

    def supply(
        self, *, lineno: Optional[int] = None, cellno: Optional[int] = None
    ) -> Location:
        """Create a new Location that contains additional information."""
        changes = {
            attr: value
            for attr, value in locals().items()
            if attr != "self" and value is not None
        }
        return replace(self, **changes)


@dataclass(eq=True, frozen=True, order=True)
class ParsedImport:
    """Import parsed from the source code."""

    name: str
    source: Location


@dataclass(eq=True, frozen=True, order=True)
class DeclaredDependency:
    """Declared dependencies parsed from configuration-containing files."""

    name: str
    source: Location


@dataclass
class UndeclaredDependency:
    """Undeclared dependency found by analysis in the 'check' module."""

    name: str
    references: List[Location]

    def render(self, *, include_references: bool) -> str:
        """Return a human-readable string representation.

        Level of detail is determined by `include_references`.
        """
        return render_problematic_dependency(
            self, "imported at" if include_references else None
        )


@dataclass
class UnusedDependency:
    """Unused dependency found by analysis in the 'check' module."""

    name: str
    references: List[Location]

    def render(self, *, include_references: bool) -> str:
        """Return a human-readable string representation.

        Level of detail is determined by `include_references`.
        """
        return render_problematic_dependency(
            self,
            "declared in" if include_references else None,
        )


def render_problematic_dependency(
    dep: Union[UndeclaredDependency, UnusedDependency], context: Optional[str]
) -> str:
    """Create text representation of the given unused or undeclared dependency."""
    ret = f"{dep.name!r}"
    if context is not None:
        unique_locations = set(dep.references)
        ret += f" {context}:" + "".join(
            f"\n    {loc}" for loc in sorted(unique_locations)
        )
    return ret
