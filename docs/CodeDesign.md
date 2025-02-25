# Requirements

## Initial goals

We want a working and usable tool that slowly adds functionality as needed.
A user runs `fawltydeps` as a command line tool in their Python
project and immediately gets some useful and actionable information.

## Boundaries

- Support all current Python versions: that means [all Python versions that have
  a stable release, and are not yet End Of Life](https://devguide.python.org/versions/).
    - Currently we support running on Python v3.9 - v3.13.
    - Since we no longer rely on running inside the same Python environment as the project being
      analyzed, it is possible for us to support analyzing projects running on even older Python versions.
- For now we support the CPython interpreter only
- OS-wise, we have concentrated on Linux. We should still run fine on
  other Unix-like systems, most notably Mac. Windows remains an open question.

# Code style

We value composability and functional style.

We want the code to be readable, testable and maintainable. That is why we use:

- code formatter `ruff format` to unify the code style,
- `ruff check` for linting
- `mypy` for typecheck
- `pytest` for testing
  to ensure this quality.

The code should be type-annotated, and functions should have docstrings.

FawltyDeps searches for imports and dependencies, and to do it efficiently,
generators are used in many places.

## Code review

Read https://www.mediawiki.org/wiki/Guidelines_for_a_healthy_code_review_culture
for a good introduction to the code review culture we want to foster in this
project.

## Tests

FawltyDeps has unit and integration tests.

We do not specifically aim for 100% coverage, but we do want to document the use
cases via tests.

Many tests use the following naming convention:
```
test_{tested_function}__{short_description}__{expected_result}
```

## Class hierarchy

Our main classes can be roughly "layered" as follows:

Level 4: `Analysis`
Level 3: `UndeclaredDependency` and `UnusedDependency`
Level 2.5: `Package`
Level 2: `ParsedImport` and `DeclaredDependency`
Level 1: `Location`

Immutability (i.e. `frozen=True`) builds from the ground up, meaning that for
objects at one layer to be immutable, then the objects below must also be
immutable. For `Location` - at the bottom - _immutability_ is a natural choice,
and for `Analysis` - at the top - _mutability_ makes more sense since this
object is built piece by piece while going through the steps of our core logic.

For the layers in between, level 2 is immutable at this point in time (as each
object is constructed in a single operation), but this might change in the
future, if we later need to extend these objects with supplemental details
(e.g. when leaving the identity mapping behind). The classes at level 3 contains
Lists of level 2 objects, and is therefore harder to argue that these should be
immutable.

Once a dataclass is made immutable (`frozen=True`) and it otherwise resembles a
[value object](https://en.wikipedia.org/wiki/Value_object), it also makes
sense to consider giving it `eq=True` and `order=True` as well, especially when
there is a natural ordering between instances of that class.
