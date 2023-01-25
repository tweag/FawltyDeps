# FawltyDeps

A dependency checker for Python.

Find undeclared 3rd-party dependencies in your Python project.

## Installation

TODO: Fill when released in PyPI

## Usage

To check the project in the current directory run:

```
fawltydeps
```

This will find imports in all the Python code under the current directory, as
well as extract dependencies declared by your project, and then report
_undeclared_ dependencies as well as _unused_ dependencies.

_Undeclared_ dependencies are dependencies that are `import`ed by the code, but
not declared by your project. For example, if you `import numpy` somewhere in
your code, but then you forget to include `numpy` in your `requirements.txt`.

_Unused_ dependencies are dependencies that your project claims to be using,
but that does not seem to be `import`ed anywhere. For example if you have
`numpy` listed in your `requirements.txt`, but you actually never `import numpy`
anywhere in your Python code.

### Available Actions

FawltyDeps provides these options for controlling what actions to perform. Only
one of these can be used at a time:

- `--check`: Report both undeclared and unused dependencies
- `--check-undeclared`: Report only unudeclared dependencies
- `--check-unused`: Report only unused dependencies
- `--list-imports`: List imports extracted from code and exit
- `--list-deps`: List declared dependencies and exit

When none of these are specified, the default action is `--check`.

### Where to find Python code

The `--code` option tells FawltyDeps where to find the Python code to parse for
`import` statements. You can pass either of these:

- a directory: FawltyDeps will find all Python scripts (`*.py`) and Jupyter
  notebooks (`*.ipynb`) under this directory.
- a single file: Either a Python script (`*.py`) or a Jupyter Notebook
  (`*.ipynb`)
- `-`: Passing a single dash (`--code=-`) tells FawltyDeps to read Python code
  from stdin.

If no `--code` option is passed, FawltyDeps will find all Python code under the
current directory, i.e. same as `--code=.`

### Where to find declared dependencies

The `--deps` option tells FawltyDeps where to look for your project's declared
dependencies. A number of file formats are supported:

- `requirements.txt`
- `pyproject.toml` (following PEP 621 or Poetry conventions)
- `setup.py` (only limited support for simple files with a single `setup()`
  call and literals passed directly to the `install_requires` and
  `extras_require` arguments)

The `--deps` option accepts either a directory, in which case FawltyDeps will go
looking for the above files under that directory. or a file, in case you want to
be explicit about where to find the declared dependencies.

If no `--deps` option is passed, FawltyDeps will look for the above files under
the current directory, i.e. same as `--deps=.`

### More help

Run `fawltydeps --help` to get the full list of available options.

## Documentation

At the start of this project, an exploration and overall project design was performed. The resulting [design document is available in this repo](./docs/DesignDoc.md). It lays out the main objective for this project as well as comparing various strategies that have been considered since the start.

In the [code design](./docs/CodeDesign.md) section of documentation we lay out rules we adopt for code architecture and quality assurance.

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

If you want to run commands individually, the sessions are defined inside
[`noxfile.py`](./noxfile.py) and should be easy to read. For example, these
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

We have a [`shell.nix`](./shell.nix) that provides Poetry in addition to all of
our supported Python versions. If you have [Nix](https://nixos.org) available
on your machine, then running:

```sh
nix-shell
```

will put you inside a shell where the Poetry virtualenv (with all development
dependencies) is activated, and all supported Python versions are available.
This also gives you isolation from whatever Python version and packages are
installed on your system.

From there, a simple `nox` will run all tests + linters against all supported
Python versions, as well as checking/formatting the code.

## Integration tests

In addition to comprehensive unit tests under `tests/`, we also verify
FawltyDeps' behavior with integration tests that (among other things) include
testing with real-world projects. To that end, we have a framework in
[`tests/test_real_projects.py`](./tests/test_real_projects.py) for downloading
and unpacking tarball of 3rd-party projects, and then run fawltydeps on them,
while verifying their output. These projects, along with the expected FawltyDeps
outputs are defined in TOML files under
[`tests/real_projects`](./tests/real_projects).

When you find a project where FawltyDeps is not doing a good job, we appreciate
you adding that project under [`tests/real_projects`](./tests/real_projects).
Look at the existing files in that directory to see how these tests work.

### Development

To give minimal working examples of supported projects we introduce [`tests/sample_projects`](./tests/sample_projects) in integration tests, where simplified version of real-world projects are stored.
For bug reports, when a user reports that `fawltydeps` not working on their project, we adopt the following process:

- the project is added to `real_projects`
- we isolate the problems/issues/features and phrase them succinctly as a sample project under `sample_projects`
- we can examine the issue more closely and start changing core logic, adding/changing unit tests along the way.

The resulting updates are introduced to `fawltydeps` and reflected in our expectations, first in the TOML for the sample project(s) and then finally in the real_projects TOML.
