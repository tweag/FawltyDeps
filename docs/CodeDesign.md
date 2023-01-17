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
