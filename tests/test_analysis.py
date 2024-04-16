"""Verify behavior of the Analysis class."""

# ruff: noqa: PLR2004,SLF001
from fawltydeps.main import calculated_once


class CalculatedOnceExample:
    """Example class using @calculated_once properties."""

    def __init__(self):
        self._memberA = None
        self._memberB = None

    @property
    @calculated_once
    def memberA(self) -> int:
        """Property that changes value if it's calculated more than once."""
        prev_value: int = 0 if self._memberA is None else self._memberA
        return prev_value + 1

    @property
    @calculated_once
    def memberB(self) -> int:
        """Property that depends on another property calculated first."""
        return self.memberA + 1


def test_calculcated_once():
    obj = CalculatedOnceExample()
    assert obj._memberA is None  # not yet calculated
    assert obj.memberA == 1  # first reference triggers calculation
    assert obj._memberA == 1  # now it's calculated

    assert obj._memberB is None  # not yet calculated
    assert obj.memberB == 2  # first reference triggers calculation
    assert obj._memberB == 2  # now it's calculated

    assert obj.memberA == 1  # subsequent references
    assert obj.memberB == 2
    assert obj._memberA == 1  # do not recalculate
    assert obj._memberB == 2

    obj = CalculatedOnceExample()
    assert obj._memberA is None  # not yet calculated
    assert obj._memberB is None
    assert obj.memberB == 2  # trigger calculation of both
    assert obj._memberA == 1  # both calculated now
    assert obj._memberB == 2

    assert obj.memberA == 1  # subsequent references
    assert obj.memberB == 2
    assert obj._memberA == 1  # do not recalculate
    assert obj._memberB == 2
