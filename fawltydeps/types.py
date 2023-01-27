"""Common types used across FawltyDeps."""

import sys
from dataclasses import dataclass, field, replace
from functools import total_ordering
from pathlib import Path
from typing import List, NamedTuple, Optional, Union

if sys.version_info >= (3, 8):
    from typing import Literal  # pylint: disable=E1101
else:
    from typing_extensions import Literal

SpecialPath = Literal["<stdin>"]
PathOrSpecial = Union[Path, SpecialPath]


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
    _sort_key: str = field(init=False, repr=False)  # see .__post_init__()

    def __post_init__(self) -> None:
        """Initialize a sort key that uniquely reflects this instance.

        This is used to compare Location objects, and determine how they sort
        relative to each other. The following must hold:
        - All instance details are captured: equal sort key => equal instance
        - Member order matters: sort by path, then cellno, then lineno
        - Unspecified members sort together, and separate from specified members
        - Paths sort alphabetically, the other members sort numerically
        """
        object.__setattr__(
            self, "_sort_key", repr((self.path, self.cellno, self.lineno))
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

    def supply(self, **changes: int) -> "Location":
        """Create a new Location that contains additional information."""
        return replace(self, **changes)


@dataclass(eq=True, frozen=True)
class ParsedImport:
    "Import parsed from the source code."
    name: str
    source: Location


class DeclaredDependency(NamedTuple):
    "Declared dependencies parsed from configuration-containing files"
    name: str
    source: Location


@dataclass
class UndeclaredDependency:
    "Undeclared dependency found by analysis in the 'check' module."
    name: str
    references: List[ParsedImport]


@dataclass
class UnusedDependency:
    "Unused dependency found by analysis in the 'check' module."
    name: str
    references: List[DeclaredDependency]
