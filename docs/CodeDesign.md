# Requirements

## Prototype

The goal of the first prototype is to reach a working and usable tool with minimal functionality.
Namely, a user would be able to run `fawltydeps` as a command line tool in their Python project.
FawltyDeps will:

- Automatically discover all Python code files and extract all the packages imported in the code.
- Automatically discover and extract from files declaring dependencies (supporting requirements.txt, setup.py and pyproject.toml).
- Use identity mapping between extracted imports and declared dependencies,
- Compare the two sets (of used vs declared dependencies) and report missing and unused dependencies.
- Support Python version 3.7 - 3.11

# Code style

We value composability and functional style.
We want the code to be readable, testable and maintainable. That is why we use:

- code formatter `black` to unify the code style,
- `pylint` and `isort` for linting
- `mypy` for typecheck
- `pytest` for testing
  to ensure this quality.

The code must be type-annotated and functions should have docstrings.

FawltyDeps searches for imports and dependencies and to do it efficiently, generators are used.

## Tests

We do not aim for 100% coverage but to document the usecases via tests. FawltyDeps has unit and integration tests.

Tests have following naming convention:

```
test_{tested_function}__{short_description}__{expected_result}
```

## Class hierarchy

Our classes can be viewed as four "layers":

Level 4: `Analysis`
Level 3: `UndeclaredDependency` and `UnusedDependency`
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
