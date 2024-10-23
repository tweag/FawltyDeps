"""A spec-compliant gitignore parser for Python."""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Tuple,
)

from fawltydeps.types import Location

if TYPE_CHECKING or sys.version_info >= (3, 9):
    CompiledRegex = re.Pattern[str]
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


class RuleMissing(RuleError):  # noqa: N818
    """A blank line or comment passed to DirectoryTraversal.ignore()."""


def parse_gitignore(full_path: Path, base_dir: Optional[Path] = None) -> Iterator[Rule]:
    """Parse the given .gitignore file and yield Rule objects.

    The 'base_dir', if given, specifies the directory relative to which the
    parsed ignore rules will be interpreted. If not given, the parent directory
    of the 'full_path' is used instead.

    See parse_gitignore_lines() for more details.
    """
    if base_dir is None:
        base_dir = full_path.parent
    with Path(full_path).open() as ignore_file:
        yield from parse_gitignore_lines(ignore_file, base_dir, full_path)


def parse_gitignore_lines(
    lines: Iterable[str],
    base_dir: Optional[Path] = None,
    file_hint: Optional[Path] = None,
) -> Iterator[Rule]:
    """Parse gitignore lines and yield corresponding Rule objects.

    A list of the returned Rule objects can be passed to match_rules() to check
    if a given path should be ignored or not.

    The 'base_dir', if given, specifies the directory relative to which the
    parsed ignore rules will be interpreted. If not given, the given rules
    cannot be anchored.
    """
    for lineno, line in enumerate(lines, start=1):
        source = None if file_hint is None else Location(file_hint, lineno=lineno)
        line = line.rstrip("\n")  # noqa: PLW2901
        try:
            yield Rule.from_pattern(line, base_dir, source)
        except RuleMissing as exc:
            # Blank lines and comments are ok when parsing multiple lines
            logger.debug(str(exc))


def match_rules(rules: List[Rule], path: Path, *, is_dir: bool) -> bool:
    """Match the given path against the given list of rules."""
    for rule in reversed(rules):
        if rule.match(path, is_dir=is_dir):
            return not rule.negated
    return False


class Rule(NamedTuple):
    """A single ignore rule, parsed from a gitignore pattern string."""

    # Basic values
    pattern: str
    regex: CompiledRegex
    # Behavior flags
    negated: bool  # Rule will (partially) negate an earlier rule
    dir_only: bool  # Rule shall match directories only
    anchored: bool  # Rule shall only match relative to .base_dir
    base_dir: Optional[Path]  # meaningful for gitignore-style behavior
    source: Optional[Location]  # Location where this rule is defined

    def __str__(self) -> str:
        return self.pattern

    def __repr__(self) -> str:
        return f"Rule({self.pattern!r}, {self.regex!r}, ...)"

    @classmethod
    def from_pattern(  # noqa: C901
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

        The base_dir argument is needed for two things:
         1. To provide the "anchor" for "anchored" rules, i.e. when a rule like
            "/foo.py" or "foo/bar" is given, the rule is interpreted relative to
            base_dir. Using anchored rules without a base_dir is not supported
            and will raise a RuleError.
         2. To support nested .gitignore files, base_dir should be set to the
            parent directory of the .gitignore file. This allows e.g. rules from
            foo/.gitignore to only apply to paths under foo/.

        For unanchored patterns that do not originate from a .gitignore file,
        the default base_dir = None is appropriate.
        """
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
            regex=fnmatch_pathname_to_regex(pattern, anchored=anchored),
            negated=negated,
            dir_only=dir_only,
            anchored=anchored,
            base_dir=base_dir,
            source=source,
        )

    def match(self, path: Path, *, is_dir: bool) -> bool:
        """Return True iff the given path should be ignored."""
        if self.base_dir:
            try:
                rel_path = path.relative_to(self.base_dir).as_posix()
            except ValueError:  # path not relative to self.base_dir
                return False
        else:
            rel_path = str(path)
        # Path() strips the trailing slash, so we need to preserve it
        # in case of directory-only negation
        if self.negated and is_dir:
            rel_path += "/"
        if rel_path.startswith("./"):
            rel_path = rel_path[2:]
        match = self.regex.search(rel_path)
        if not match:
            return False

        # Rule matches given path or one of its parent dirs
        return (
            not self.dir_only  # rule matches and is not dir-specific
            or is_dir  # path is a dir, so rule matches nonetheless
            or match.end() < match.endpos  # rule matches only if parent dir
        )


# Static regex fragments used below:
SEPS = [re.escape(os.sep)] + ([] if os.altsep is None else [re.escape(os.altsep)])
SEPS_GROUP = "[" + "|".join(SEPS) + "]"
NONSEP = rf"[^{'|'.join(SEPS)}]"


# Frustratingly, python's fnmatch doesn't provide the FNM_PATHNAME option that
# .gitignore's behavior depends on, so convert the pattern to a regex instead.
def fnmatch_pathname_to_regex(pattern: str, *, anchored: bool = False) -> CompiledRegex:
    """Convert the given fnmatch-style pattern to the equivalent regex.

    Implements fnmatch style-behavior, as though with FNM_PATHNAME flagged;
    the path separator will not match shell-style '*' and '.' wildcards.
    """
    result = []

    def handle_character_set(pattern: str) -> Tuple[str, str]:
        assert pattern.startswith("[")  # noqa: S101, sanity check precondition
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
    result.append("$")

    return re.compile("".join(result))
