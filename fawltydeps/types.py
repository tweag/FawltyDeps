"""Common types used across FawltyDeps."""

import sys
from dataclasses import asdict, dataclass, field, replace
from functools import total_ordering
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from fawltydeps.utils import hide_dataclass_fields

if sys.version_info >= (3, 8):
    from typing import Literal  # pylint: disable=no-member
else:
    from typing_extensions import Literal

SpecialPath = Literal["<stdin>"]
PathOrSpecial = Union[SpecialPath, Path]
TomlData = Dict[str, Any]  # type: ignore


class UnparseablePathException(Exception):
    """Exception type when alleged path (deps or code) can't be parsed"""

    def __init__(self, ctx: str, path: Path):
        self.msg = f"{ctx}: {path}"


@total_ordering
@dataclass(frozen=True)
class Location:
    """Reference to a source location, e.g. a file, a line within a file, etc.

    This is deliberately kept flexible, and the intention is for instances to
    be associated with data that originates from some input file (or even
    something read from a non-file like stdin), and carry as much or as little
    information as is appropriate about the _source_ of the associated data.

    Examples include:
     - Referring to a specific line (+ column?) in a file of Python source code
     - Referring to a line number in anonymous Python code read from stdin
     - Referring to a file of dependency information (e.g. pyproject.toml),
       where a specific line number is not available (for any reason)
     - Referring to a specific cell in a Jupyter notebook.

    Instances have a string representation that reflect the level of detail
    provided, and they are sortable.
    """

    path: PathOrSpecial
    cellno: Optional[int] = None
    lineno: Optional[int] = None

    # It would be ideal to use the automatic __eq__, __lt__, etc. methods that
    # @dataclass can provide for us, thus making Location objects automatically
    # orderable/sortable. However, the automatic implementations end up directly
    # comparing tuples of our members, which fails when some of those members
    # are None, with errors like e.g.: TypeError: '<' not supported between
    # instances of 'PosixPath' and 'NoneType'.
    # Instead, we must implement our own. Do so based on a comparable/sortable
    # string created/cached together with the instance.
    _sort_key: Tuple[str, int, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize a sort key that uniquely reflects this instance.

        This is used to compare Location objects, and determine how they sort
        relative to each other. The following must hold:
        - All instance details are captured: equal sort key => equal instance
        - Member order matters: sort by path, then cellno, then lineno
        - Unspecified members sort together, and separate from specified members
        - Paths sort alphabetically, the other members sort numerically
        """
        sortable_tuple = (
            repr(self.path),
            -1 if self.cellno is None else self.cellno,
            -1 if self.lineno is None else self.lineno,
        )
        object.__setattr__(self, "_sort_key", sortable_tuple)

        # Do magic to hide unset/None members from JSON representation
        unset = [attr for attr, value in asdict(self).items() if value is None]
        hide_dataclass_fields(self, "_sort_key", *unset)

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

    def supply(self, **changes: int) -> "Location":
        """Create a new Location that contains additional information."""
        return replace(self, **changes)


@dataclass(eq=True, frozen=True, order=True)
class ParsedImport:
    """Import parsed from the source code."""

    name: str
    source: Location


@dataclass(eq=True, frozen=True, order=True)
class DeclaredDependency:
    """Declared dependencies parsed from configuration-containing files"""

    name: str
    source: Location


@dataclass
class UndeclaredDependency:
    """Undeclared dependency found by analysis in the 'check' module."""

    name: str
    references: List[Location]

    def render(self, include_references: bool) -> str:
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

    def render(self, include_references: bool) -> str:
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
