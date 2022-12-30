# FawltyDeps

A dependency checker for Python.

Find undeclared 3rd-party dependencies in your Python project.

# Installation

TODO: Fill when released in PyPI

# Usage

To check the project in the current directory run:

```
fawltydeps
```

Options available:

```
> fawltydeps --help
usage: fawltydeps [-h] [--code CODE] [-v] [-q]

Find undeclared 3rd-party dependencies in your Python project.

options:
  -h, --help     show this help message and exit
  --code CODE    Code to parse for import statements (file or directory, use '-' to read code from stdin; defaults to the current directory)
  -v, --verbose  Increase log level (WARNING by default, -v: INFO, -vv: DEBUG)
  -q, --quiet    Decrease log level (WARNING by default, -q: ERROR, -qq: FATAL)
```

# Documentation

TODO: Add design doc

[Code design](./docs/CodeDesign.md)

# Development

The project uses [Poetry](https://python-poetry.org/). Install Poetry, and run:

```
poetry shell
```

To install the project run:

```
poetry install
```

Inside the shell you have a Python virtual environment with all dependencies declared in pyproject.toml installed.
To test, typecheck and ensure code formatting you just run:

```
pytest          # tests
mypy            # type annotations checks
black --check   # formater checks
pylint          # linter
isort           # import sort
```

TODO: explain how to run CI locally when [#15](https://github.com/tweag/FawltyDeps/issues/15) is completed
