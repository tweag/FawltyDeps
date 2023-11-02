"""A spec-compliant gitignore parser for Python."""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Iterable, NamedTuple, Optional, Tuple

from fawltydeps.types import Location

if TYPE_CHECKING or sys.version_info >= (3, 9):
    CompiledRegex = re.Pattern[str]  # pylint: disable=unsubscriptable-object
else:  # re.Pattern not subscriptable before Python 3.9
    CompiledRegex = re.Pattern

logger = logging.getLogger(__name__)


class RuleError(ValueError):
    """Error while parsing an ignore pattern in DirectoryTraversal.ignore()."""

    def __init__(self, msg: str, pattern: str, source: Optional[Location] = None):
        self.msg = msg
        self.pattern = pattern
        self.source = source

    def __str__(self) -> str:
        if self.source is not None:
            return f"{self.msg}: {self.pattern!r} ({self.source})"
        return f"{self.msg}: {self.pattern!r}"


class RuleMissing(RuleError):
    """A blank line or comment passed to DirectoryTraversal.ignore()."""


def parse_gitignore(
    full_path: Path, base_dir: Optional[Path] = None
) -> Callable[[Path, bool], bool]:
    """Parse the given .gitignore file and return the resulting rules checker.

    The 'base_dir', if given, specifies the directory relative to which the
    parsed ignore rules will be interpreted. If not given, the parent directory
    of the 'full_path' is used instead.

    See parse_gitignore_lines() for more details.
    """
    if base_dir is None:
        base_dir = full_path.parent
    with open(full_path) as ignore_file:
        return parse_gitignore_lines(ignore_file, base_dir, full_path)


def parse_gitignore_lines(
    lines: Iterable[str],
    base_dir: Optional[Path] = None,
    file_hint: Optional[Path] = None,
) -> Callable[[Path, bool], bool]:
    """Parse gitignore lines and return the resulting rules checker.

    The return value is a predicate for paths to ignore, i.e. a callable that
    returns True/False based on whether a given path should be ignored or not.

    The 'base_dir', if given, specifies the directory relative to which the
    parsed ignore rules will be interpreted. If not given, the given rules
    cannot be anchored.
    """
    rules = []
    for lineno, line in enumerate(lines, start=1):
        source = None if file_hint is None else Location(file_hint, lineno=lineno)
        line = line.rstrip("\n")
        try:
            rules.append(Rule.from_pattern(line, base_dir, source))
        except RuleMissing as exc:
            # Blank lines and comments are ok when parsing multiple lines
            logger.debug(str(exc))

    if not any(r.negated for r in rules):

        def handle_straightforward(file_path: Path, is_dir: bool) -> bool:
            return any(r.match(file_path, is_dir) for r in rules)

        return handle_straightforward

    # We have negation rules. We can't use a simple "any" to evaluate them.
    # Later rules override earlier rules.
    def handle_negation(file_path: Path, is_dir: bool) -> bool:
        for rule in reversed(rules):
            if rule.match(file_path, is_dir):
                return not rule.negated
        return False

    return handle_negation


class Rule(NamedTuple):
    """A single ignore rule, parsed from a gitignore pattern string."""

    # Basic values
    pattern: str
    regex: CompiledRegex
    # Behavior flags
    negated: bool
    dir_only: bool
    anchored: bool
    base_dir: Optional[Path]  # meaningful for gitignore-style behavior
    source: Optional[Location]

    def __str__(self) -> str:
        return self.pattern

    def __repr__(self) -> str:
        return f"Rule({self.pattern!r}, {self.regex!r}, ...)"

    @classmethod
    def from_pattern(
        cls,
        pattern: str,
        base_dir: Optional[Path] = None,
        source: Optional[Location] = None,
    ) -> Rule:
        """Build a Rule object from the given .gitignore pattern string.

        Take a .gitignore match pattern, such as "*.py[cod]" or "**/*.bak", and
        return an instance suitable for matching against files and directories.
        Patterns which do not match files, such as comments and blank lines,
        will raise RuleMissing, and other errors while parsing will raise
        RuleError.

        Because git allows for nested .gitignore files, a base_dir value is
        required for correct behavior. The base path should be absolute.
        """
        if base_dir is not None and not base_dir.is_absolute():
            raise RuleError("base_dir must be absolute", str(base_dir), source)

        # Store the exact pattern for our repr and string functions
        orig_pattern = pattern

        # Discard comments and separators
        if pattern.strip() == "" or pattern[0] == "#":
            raise RuleMissing("No rule found", pattern, source)
        # Strip leading bang before examining double asterisks
        negated = pattern.startswith("!")
        if negated:
            pattern = pattern[1:]

        # Multi-asterisks not surrounded by slashes (or at the start/end) should
        # be treated like single-asterisks.
        pattern = re.sub(r"([^/])\*{2,}", r"\1*", pattern)
        pattern = re.sub(r"\*{2,}([^/])", r"*\1", pattern)

        # Special-casing '/', which doesn't match any files or directories
        if pattern.rstrip() == "/":
            raise RuleMissing("Pattern does not match anything", pattern, source)

        dir_only = pattern.endswith("/")
        # A slash is a sign that we're tied to the base_dir of our rule set.
        anchored = "/" in pattern[:-1]
        if pattern.startswith("/"):
            pattern = pattern[1:]
        if pattern.startswith("**"):
            pattern = pattern[2:]
            anchored = False
        if pattern.startswith("/"):
            pattern = pattern[1:]
        if pattern.endswith("/"):
            pattern = pattern[:-1]
        # patterns with leading hashes or exclamation marks are escaped with a
        # backslash in front, unescape it
        if pattern.startswith(("\\#", "\\!")):
            pattern = pattern[1:]
        # trailing spaces are ignored unless they are escaped with a backslash
        while pattern.endswith(" ") and not pattern.endswith("\\ "):
            pattern = pattern[:-1]
        pattern = pattern.replace("\\ ", " ")  # unescape remaining spaces

        if anchored and base_dir is None:
            raise RuleError("Anchored pattern without base_dir", pattern, source)

        return cls(
            pattern=orig_pattern,
            regex=fnmatch_pathname_to_regex(pattern, dir_only, negated, anchored),
            negated=negated,
            dir_only=dir_only,
            anchored=anchored,
            base_dir=base_dir,
            source=source,
        )

    def match(self, abs_path: Path, is_dir: bool) -> bool:
        """Return True iff the given 'abs_path' should be ignored."""
        matched = False
        if self.base_dir:
            rel_path = str(abs_path.relative_to(self.base_dir))
        else:
            rel_path = str(abs_path)
        # Path() strips the trailing slash, so we need to preserve it
        # in case of directory-only negation
        if self.negated and is_dir:
            rel_path += "/"
        if rel_path.startswith("./"):
            rel_path = rel_path[2:]
        if self.regex.search(rel_path):
            matched = True
        return matched


# Static regex fragments used below:
SEPS = [re.escape(os.sep)] + ([] if os.altsep is None else [re.escape(os.altsep)])
SEPS_GROUP = "[" + "|".join(SEPS) + "]"
NONSEP = rf"[^{'|'.join(SEPS)}]"


# Frustratingly, python's fnmatch doesn't provide the FNM_PATHNAME option that
# .gitignore's behavior depends on, so convert the pattern to a regex instead.
def fnmatch_pathname_to_regex(
    pattern: str, dir_only: bool, negated: bool, anchored: bool = False
) -> CompiledRegex:  # pylint: disable=unsubscriptable-object
    """Convert the given fnmatch-style pattern to the equivalent regex.

    Implements fnmatch style-behavior, as though with FNM_PATHNAME flagged;
    the path separator will not match shell-style '*' and '.' wildcards.
    """
    result = []

    def handle_character_set(pattern: str) -> Tuple[str, str]:
        assert pattern.startswith("[")  # precondition
        try:
            end = pattern.index("]")
        except ValueError:  # "]" not found
            return "\\[", pattern[1:]

        inside, rest = pattern[1:end], pattern[end + 1 :]
        inside = inside.replace("\\", "\\\\").replace("/", "")
        if inside.startswith("^"):  # -> literal "^"
            inside = "\\" + inside
        elif inside.startswith("!"):  # -> negated character set -> [^...]
            inside = "^" + inside[1:]
        return f"[{inside}]", rest

    handlers: Dict[str, Callable[[str], Tuple[str, str]]] = {
        # pattern prefix -> callable that given pattern returns (result, rest)
        "**/": lambda pattern: (f"(.*{SEPS_GROUP})?", pattern[3:]),
        "**": lambda pattern: (".*", pattern[2:]),
        "*": lambda pattern: (f"{NONSEP}*", pattern[1:]),
        "?": lambda pattern: (NONSEP, pattern[1:]),
        "/": lambda pattern: (SEPS_GROUP, pattern[1:]),
        "[": handle_character_set,
        "": lambda pattern: (re.escape(pattern[0]), pattern[1:]),
    }
    while pattern:
        for prefix, func in handlers.items():
            if pattern.startswith(prefix):
                fragment, pattern = func(pattern)
                result.append(fragment)
                break
        else:
            raise RuntimeError("FRAGMENTS is incomplete!")

    if anchored:
        result.insert(0, "^")
    else:
        result.insert(0, f"(^|{SEPS_GROUP})")
    if not dir_only:
        result.append("$")
    elif dir_only and negated:
        result.append("/$")
    else:
        result.append("($|\\/)")

    return re.compile("".join(result))
