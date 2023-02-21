# FawltyDeps

A dependency checker for Python.

Find _undeclared_ and/or _unused_ 3rd-party dependencies in your Python project.

## Key Concepts

- **_undeclared_ dependency**: a package that's used (in particular, `import`ed) by a project and which lacks a corresponding declaration to ensure that it's available.
  For example, you `import numpy`, but you've forgotten to include `numpy` in your `requirements.txt`.
  Pragmatically, this means the project is prone to runtime errors.
- **_unused_ dependency**: a package that's declared as necessary for a project but which is never used by project code.
  For example, you have `numpy` listed in your `requirements.txt`, but you never actually `import numpy`.
  Pragmatically, this means that project installation may consume more space than needed and will be more likely to break with future software releases; in short, these are costs paid for no benefit.

## Installation

The library is distributed with PyPI, so simply:

```
pip install fawltydeps
```

or any other way to install Python packages from PyPI should be enough to make it available in your environment.

Consider adding `fawltydeps` to your development dependencies, to help you catch undeclared and unused dependencies in your projects.

## Usage

To check the project in the current directory run:

```
fawltydeps
```

This will find imports in all the Python code under the current directory,
extract dependencies declared by your project, and then report
[_undeclared_ and _unused_ dependencies](#key-concepts).

### Available Actions

FawltyDeps provides the following options for controlling what actions to perform. Only
one of these can be used at a time:

- `--check`: Report both undeclared and unused dependencies
- `--check-undeclared`: Report only undeclared dependencies
- `--check-unused`: Report only unused dependencies
- `--list-imports`: List third-party imports extracted from the project
- `--list-deps`: List declared dependencies extracted from the project

When none of these are specified, the default action is `--check`.

### Where to find Python code

The `--code` option tells FawltyDeps where to find the Python code to parse for
`import` statements. You can pass either of these:

- a single file: Either a Python file (`*.py`) or a Jupyter Notebook (`*.ipynb`)
- a directory: FawltyDeps will find all Python files and Jupyter notebooks under this directory.
- `-`: Passing a single dash (`--code=-`) tells FawltyDeps to read Python code
  from stdin.

If no `--code` option is passed, FawltyDeps will find all Python code under the
current directory, i.e. same as `--code=.`

### Where to find declared dependencies

The `--deps` option tells FawltyDeps where to look for your project's declared
dependencies. A number of file formats are supported:

- `*requirements*.txt` and `*requirements*.in`
- `pyproject.toml` (following PEP 621 or Poetry conventions)
- `setup.py` (only limited support for simple files with a single `setup()`
  call and no computation involved for setting the `install_requires` and
  `extras_require` arguments)
- `setup.cfg`

The `--deps` option accepts either a directory, in which case FawltyDeps will go
looking for the above files under that directory. or a file, in case you want to
be explicit about where to find the declared dependencies.

If no `--deps` option is passed, FawltyDeps will look for the above files under
the current directory, i.e. same as `--deps=.`

### Ignoring irrelevant results

There may be `import` statements in your code that should not be considered an
undeclared dependency. This might happen if you for example do a conditional
`import` with a `try: ... except ImportError: ...` block (or similar).
FawltyDeps is not able to recognize whether these dependencies should have been
declared or not, but you can ask for them to be ignored with the
`--ignore-undeclared` option, for example:
`--ignore-undeclared some_module some_other_module`

Conversely, there may be dependencies that you have declared without intending
to `import` them. This is often the case for developer tools like Black or Mypy
that are part of your project's development environment.
FawltyDeps cannot automatically tell which of your declared dependencies are
meant to be `import`ed or not, but you ask for specific deps to be ignored with
the `--ignore-unused` option, for example:
`--ignore-unused black mypy`

### Output formats

The default output from FawltyDeps is a summary outlining the relevant
dependencies found (according to the selected actions).
However you can also ask for more information from FawltyDeps:

- `--summary`: Default (human-readable) summary output
- `--detailed`: Longer (human-readable) output that includes the location of
  the relevant dependencies.
- `--json`: Verbose JSON-formatted output for other tools to consume and
  process further.

Only one of these options can be used at a time.

### More help

Run `fawltydeps --help` to get the full list of available options.

## Configuration

You can use a `[tool.fawltydeps]` section in `pyproject.toml` to configure the
default behavior of FawltyDeps. Here's a fairly comprehensive example:

```toml
[tool.fawltydeps]
code = "myproject"  # Only search for imports under ./myproject
deps = "pyproject.toml"  # Only look for declared dependencies here
ignore_unused = ["black"]  # We use `black`, but we don't intend to import it
output_format = "human_detailed"  # Detailed report by default
```

Here is a complete list of configuration directives we support:

- `actions`: A list of one or more of these actions to perform: `list_imports`,
  `list_deps`, `check_undeclared`, `check_unused`. The default behavior
  corresponds to `actions = ["check_undeclared", "check_unused"]`.
- `code`: A file or directory containing the code to parse for import statements.
  Defaults to the current directory, i.e. like `code = .`.
- `deps`: A file or directory containing the declared dependencies.
  Defaults to the current directory, i.e. like `deps = .`.
- `output_format`: Which output format to use by default. One of `human_summary`,
  `human_detailed`, or `json`.
  The default corresponds to `output_format = "human_summary"`.
- `ignore_undeclared`: A list of specific dependencies to ignore when reporting
  undeclared dependencies, for example: `["some_module", "some_other_module"]`.
  The default is the empty list: `ignore_undeclared = []`.
- `ignore_unused`: A list of specific dependencies to ignore when reporting
  unused dependencies, for example: `["black", "mypy"]`.
  The default is the empty list: `ignore_unused = []`.
- `verbosity`: An integer controlling the default log level of FawltyDeps:
  - `-2`: Only `CRITICAL`-level log messages are shown.
  - `-1`: `ERROR`-level log messages and above are shown.
  - `0`: `WARNING`-level log messages and above are shown. This is the default.
  - `1`: `INFO`-level log messages and above are shown.
  - `2`: All log messages (including `DEBUG`) are shown.

### Environment variables

In addition to configuring FawltyDeps via `pyproject.toml` as show above, you
may also pass the above configuration directives via the environment, using a
`fawltydeps_` prefix. For example, to enable JSON output via the environment,
set `fawltydeps_output_format=json` in FawltyDeps' environment.

### Configuration cascade

- Command-line options take precedence, and override corresponding settings
  passed via the environment or `pyproject.toml`.
- Environment variables override corresponding settings from `pyproject.toml`.
- Configuration in `pyproject.toml` override only the ultimate hardcoded defaults.
- The ultimate defaults when no cutomizations takes place are hardcoded inside
  FawltyDeps, and are documented above.

## Documentation

This project began with an exploration and design phase, yielding this [design document](./docs/DesignDoc.md), which lays out the main objective for this project and compares various strategies considered

In the [code design](./docs/CodeDesign.md) section of documentation we lay out rules which we adopt to guide code architecture decisions and maintain code quality as the project evolves.

## Development

### Poetry

The project uses [Poetry](https://python-poetry.org/). Install Poetry, and then
run:

```sh
poetry install --with=dev
```

to create a virtualenv with all (development) dependencies installed.

From there you can run:

```sh
poetry shell
```

to jump into a development shell with this virtualenv activated. Here you will
have all the dependencies declared in our [`pyproject.toml`](./pyproject.toml)
installed. (Without this shell activated you will have to prefix the more
specific commands below with `poetry run ...`).

### Nox

We use [Nox](https://nox.thea.codes/en/stable/) for test/workflow automation:

```sh
nox --list        # List sessions
nox               # Run all available sessions
nox -R            # Run all available sessions, while reusing virtualenvs (i.e. faster)
nox -s tests      # Run unit tests on supported Python versions (that are available)
nox -s tests-3.7  # Run unit tests on Python v3.7 (assuming it is available locally)
nox -s integration_tests-3.11  # Run integration tests on Python 3.11
nox -s lint       # Run linters (mypy + pylint) on all supported Python versions
nox -s format     # Check formatting (isort + black)
nox -s reformat   # Fix formatting (isort + black)
```

If you want to run a command individually, the corresponding session is defined inside
[`noxfile.py`](./noxfile.py). For example, these
commands will work:

```sh
pytest                   # Run unit tests
pytest -m integration    # Run integration tests
mypy                     # Run static type checking
pylint fawltydeps tests  # Run Pylint
isort fawltydeps tests   # Fix sorting of import statements
black .                  # Fix code formatting
```

### Shortcut: Nix

We have a [`shell.nix`](./shell.nix) which provides Poetry in addition to all of
our supported Python versions. If you have [Nix](https://nixos.org) available
on your machine, then running:

```sh
nix-shell
```

will put you inside a shell where the Poetry virtualenv (with all development
dependencies) is activated, and all supported Python versions are available.
This also provides isolation from whatever Python version(s) and packages are
installed on your system.

From there, a simple `nox` will run all tests + linters against all supported
Python versions, as well as checking/formatting the code.

## Integration tests

In addition to comprehensive unit tests under `tests/`, we also verify
FawltyDeps' behavior with integration tests which (among other things) include
testing with real-world projects. To that end, we have a framework in
[`tests/test_real_projects.py`](./tests/test_real_projects.py) for downloading
and unpacking tarballs of 3rd-party projects, and then running fawltydeps on them,
while verifying their output. These projects, along with the expected FawltyDeps
outputs, are defined in TOML files under
[`tests/real_projects`](./tests/real_projects).

## Contributing
For bug reports, when a user reports that `fawltydeps` does not work on their project, we adopt the following process:

- The project is added to `real_projects`.
- We isolate the problems/issues/features and define/express them succinctly as a sample project under `sample_projects`.
- We examine the issue more closely and update core logic, adding/altering unit tests along the way.

The resulting updates are introduced to `fawltydeps` and reflected in our expectations, first in the TOML for the sample project(s) and then finally in the `real_projects` TOML.

If you find a project where FawltyDeps is not doing a good job, we would appreciate
if you add that project under [`tests/real_projects`](./tests/real_projects).
To see how these tests work, look at the existing files in that directory.
