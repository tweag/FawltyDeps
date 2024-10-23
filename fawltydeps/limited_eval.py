"""Provide limited evaluation capabilities for setup.py files."""

import ast
import logging
import sys
from typing import Dict, List, Union

from fawltydeps.types import Location

logger = logging.getLogger(__name__)


# Types of variable values that we currently recognize
TrackedValue = Union[str, List[str], Dict[str, "TrackedValue"]]


class CannotResolve(Exception):  # noqa: N818
    """Error raised when we fail to resolve the value of a variable."""

    def __init__(self, node: ast.AST, source: Location):
        super().__init__(node)
        self.node = node
        self.source = source


class VariableTracker:
    """Track variable assignments in a piece of Python code.

    This is about evaluating just enough of a setup.py file to correctly
    interpret some common patterns for declaring dependencies, but _without_
    actually executing the setup.py file (with potential security implications).
    """

    def __init__(self, source: Location) -> None:
        self.vars: Dict[str, TrackedValue] = {}
        self.source: Location = source

    def _show(self, node: ast.AST) -> str:
        """Human-readable representation of this node, mostly for debug logs."""
        if sys.version_info >= (3, 9):
            code = ast.unparse(node)
        else:
            code = "<code>"
        return f"{code} @ {self.source.supply(lineno=node.lineno)}"  # type: ignore[attr-defined]

    def _dump(self, node: ast.AST) -> str:
        """Human-readable debug dump of this node."""
        return f"{ast.dump(node)} from {self._show(node)}"

    def evaluate(self, node: ast.AST) -> None:
        """Find and record assignments in the given code.

        For now, we only detect the very simplest patterns here. We're not
        (at this point in time) trying to do a full-fledged evaluation of
        the entire setup.py.
        """
        if isinstance(node, ast.Assign):
            logger.debug(f"Got {self._dump(node)}")
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store):
                    try:
                        self.vars[target.id] = self.resolve(node.value)
                    except CannotResolve as exc:
                        logger.warning(
                            f"Failed to parse assignment of {target.id!r}: {self._dump(exc.node)}",
                        )
                else:
                    logger.warning(f"Don't known how to parse {self._dump(node)}")
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            logger.warning(f"Don't know how to parse {self._dump(node)}!")

    def resolve(self, node: ast.AST) -> TrackedValue:
        """Convert a literal or a variable reference to the ultimate value.

        Raise CannotResolve if we're unable to arrive at the ultimate value,
        for example in these cases:
            - A kind of literal that we don't (yet) support.
            - A variable reference that we have been unable to resolve.
            - Anything that is not a literal or a variable reference, e.g. the
              result of a function call.
        """
        logger.debug(f"Resolving {self._dump(node)}")
        # Python v3.8 changed from ast.Str to ast.Constant
        if isinstance(node, (ast.Constant, ast.Str)):
            return str(ast.literal_eval(node))
        if isinstance(node, ast.List):
            return [str(self.resolve(element)) for element in node.elts]
        if isinstance(node, ast.Dict):
            return {
                str(self.resolve(key)): self.resolve(val)
                for key, val in zip(node.keys, node.values)
                if isinstance(key, ast.AST)
            }
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in self.vars
        ):
            return self.vars[node.id]

        logger.warning(f"Unable to resolve {self._dump(node)}")
        raise CannotResolve(node, self.source.supply(lineno=node.lineno))  # type: ignore[attr-defined]
