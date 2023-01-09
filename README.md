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

## Documentation

At the start of this project, an exploration and overall project design was performed. The resulting [design document is available in this repo](./docs/DesignDoc.md). It lays out the main objective for this project as well as comparing various strategies that have been considered since the start.

In the [code design](./docs/CodeDesign.md) section of documenation we lay out rules we adopt for code architecture and quality assurance.

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
have all the dependencies declared in our `pyproject.toml` installed. (Without
this shell activated you will have to prefix the more specific commands below
with `poetry run ...`).

### Nox

We use [Nox](https://nox.thea.codes/en/stable/) for test/workflow automation:

```sh
nox --list        # List sessions
nox               # Run all available sessions
nox -R            # Run all available sessions, while reusing virtualenvs (i.e. faster)
nox -s tests      # Run test suite on supported Python versions (that are available)
nox -s tests-3.7  # Run test suite on Python v3.7 (assuming it is available locally)
nox -s lint       # Run linters (mypy + pylint) on all supported Python versions
nox -s format     # Check formatting (isort + black)
nox -s reformat   # Fix formatting (isort + black)
```

If you want to run commands individually, the sessions are defined inside
`noxfile.py` and should be easy to read. For example, these commands will work:

```sh
pytest                   # Run test suite
mypy                     # Run static type checking
pylint fawltydeps tests  # Run Pylint
isort fawltydeps tests   # Fix sorting of import statements
black .                  # Fix code formatting
```

### Shortcut: Nix

We have a `shell.nix` that provides Poetry in addition to all of our supported
Python versions. If you have [Nix](https://nixos.org) available on your machine,
then running:

```sh
nix-shell
```

will put you inside a shell where the Poetry virtualenv (with all development
dependencies) is activated, and all supported Python versions are available.
This also gives you isolation from whatever Python version and packages are
installed on your system.

From there, a simple `nox` will run all tests + linters against all supported
Python versions, as well as checking/formatting the code.
