# Code design

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
