[![PyPI Latest Release](https://img.shields.io/pypi/v/fawltydeps.svg)](https://pypi.org/project/fawltydeps/) [![Supported Python versions](https://img.shields.io/pypi/pyversions/fawltydeps.svg)](https://pypi.org/project/fawltydeps/) ![Build](https://img.shields.io/github/actions/workflow/status/tweag/fawltydeps/ci.yaml) [![Licence](https://img.shields.io/pypi/l/fawltydeps.svg)](https://pypi.org/project/fawltydeps/) [![Code of conduct](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](code_of_conduct.md)

# FawltyDeps

FawltyDeps is a dependency checker for Python that finds _undeclared_ and/or
_unused_ 3rd-party dependencies in your Python project.
The name is inspired by the Monty Python-adjacent
[Fawlty Towers](https://en.wikipedia.org/wiki/Fawlty_Towers) sitcom.

![FawltyDeps demo](https://github.com/tweag/FawltyDeps/raw/main/docs/fawltydeps_demo_tqdm.gif)

## Table of contents

[Key Concepts](#key-concepts)

[Installation](#installation)

[Usage](#usage)

[Configuration](#configuration)

[Documentation](#documentation)

[Development](#development)

[Integration tests](#integration-tests)

[FAQ](#faq)

## Key Concepts

- **_undeclared_ dependency**: a package that's used (in particular, `import`ed) by a project and which lacks a corresponding declaration to ensure that it's available.
  For example, you `import numpy`, but you've forgotten to include `numpy` in your `requirements.txt`.
  Pragmatically, this means the project is prone to runtime errors.
- **_unused_ dependency**: a package that's declared as necessary for a project but which is never used by project code.
  For example, you have `numpy` listed in your `requirements.txt`, but you never actually `import numpy`.
  Pragmatically, this means that project installation may consume more space than needed and will be more likely to break with future software releases; in short, these are costs paid for no benefit.

## Installation

The library is distributed with PyPI, so simply:

```sh
pip install fawltydeps
```

or any other way to install Python packages from PyPI should be enough to make it available in your environment.

Consider adding `fawltydeps` to your development dependencies, to help you catch undeclared and unused dependencies in your projects.

## Usage

To check the project in the current directory run:

```sh
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

### Where to find code and dependency declarations

By default, FawltyDeps will look for Python code (`*.py` and `*.ipynb`) and
dependency declarations (see list of supported files below) under the current
directory. If you want FawltyDeps to look elsewhere, you can pass a different
directory (aka `basepath`) as a positional argument:

```sh
fawltydeps my_project/
```

If you want to separately declare the source of the code and the source of the
dependencies, you may use the `--code` and `--deps` options documented in the
next section. In short, giving the `basepath` positional argument is equivalent
to passing both the `--code` and the `--deps` options, like this:

```sh
fawltydeps --code my_project/ --deps my_project/
```

#### Where to find Python code

The `--code` option tells FawltyDeps where to find the Python code to parse for
`import` statements. You can pass any number of these:

- a single file: Either a Python file (`*.py`) or a Jupyter Notebook (`*.ipynb`)
- a directory: FawltyDeps will find all Python files and Jupyter notebooks under this directory.
- `-`: Passing a single dash (`--code=-`) tells FawltyDeps to read Python code
  from stdin.

If no `--code` option is passed, FawltyDeps will find all Python code under the
`basepath`, if given, or the current directory (i.e. same as `--code=.`).
To include both code from stdin (`import foo`) and a file path (`file.py`), use:

```sh
echo "import foo" | fawltydeps --list-imports --code - file.py
```

#### Where to find declared dependencies

The `--deps` option tells FawltyDeps where to look for your project's declared
dependencies. A number of file formats are supported:

- `*requirements*.txt` and `*requirements*.in`
- `pyproject.toml` (following PEP 621 or Poetry conventions)
- `setup.py` (only limited support for simple files with a single `setup()`
  call and no computation involved for setting the `install_requires` and
  `extras_require` arguments)
- `setup.cfg`

The `--deps` option accepts a space-separated list of files or directories.
Each file will be parsed for declared dependencies; each directory will
be searched, parsing all of the supported files (see the above list) found
within. You would typically want to pass individual files, if you want to
be explicit about where to find the declared dependencies.

If no `--deps` option is passed, FawltyDeps will look for the above files under
the `basepath`, if given, or the current directory (i.e. same as `--deps .`).

### Resolving dependencies

When FawltyDeps looks for undeclared and unused dependencies, it needs to match
`import` statements in your code with corresponding package dependencies
declared in your project configuration.

To solve this, FawltyDeps adopts several strategies: mapping provided by the user,
identity mapping, and most powerful of all - using your python environment.

#### Python environment mapping

FawltyDeps looks at the packages installed in your _current
Python environment_ and what import names each of them provide in order to
correctly match your dependencies against your imports.

The _current Python environment_ in this case is the environment in which
FawltyDeps itself is installed. This works well when you, for example,
`pip install fawltydeps` into the same virtualenv as your project dependencies.

If you instead want FawltyDeps to look into a _different_ Python environment for
mapping dependencies to import names, you can use the `--pyenv` option,
for example:

```sh
fawltydeps --code my_package/ --deps pyproject.toml --pyenv .venv/
```

This will tell FawltyDeps:

- to look for `import` statements in the `my_package/` directory,
- to parse dependencies from `pyprojects.toml`, and
- to use the Python environment at `.venv/` to map dependency names in
  `pyproject.toml` into import names used in your code under `my_package/`

You can use `--pyenv` multiple times to have FawltyDeps look for packages in
multiple Python environments. When mapping a dependency into import names,
FawltyDeps will then use the union of all imports provided by all matching
packages across those Python environments as valid import names for that
dependency.

#### Identity mapping

When FawltyDeps is unable to find an installed package that corresponds to a
declared dependency, FawltyDeps will fall back to an "identity mapping", where
it _assumes_ that the dependency provides a single import of the same name,
i.e. it will expect that when you depend on `some_package`, then that should
correspond to `import some_package` statements in your code.

This fallback assumption is not always correct, but it allows FawltyDeps to
produce results (albeit sometimes inaccurate) when the current Python
environment does not contain all of your declared dependencies. Please see
FAQ below about [why FawltyDeps must run in the same Python environment as your
project dependencies](#why-must-fawltydeps-run-in-the-same-python-environment-as-my-project-dependencies).

#### User-defined mapping

You may define your mapping by providing a toml file with package to imports mapping,
`my_mapping.toml`:

```toml
my-package = ["mpkg"]
scikit-learn = ["sklearn"]
multiple-modules = ["module1", "module2"]
```

To use your mapping, run:

```sh
fawltydeps --custom-mapping-file my_mapping.toml
```

FawltyDeps will parse `my_mapping.toml` file and use extracted mapping for matching dependencies to imports.

You may also place the custom mapping in the `pyproject.toml` file of your project, inside a `[tool.fawltydeps.custom_mapping]` section, like this:

```toml
[tool.fawltydeps.custom_mapping]
my-package = ["mpkg"]
scikit-learn = ["sklearn"]
multiple-modules = ["module1", "module2"]
```

Caution when using your mapping is advised. The user-defined mapping takes precedence over all other resolving strategies.
If the mapping file has some stale mapping entries, they will not be resolved by
Python environment resolver (which in general is the most accurate).

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
code = ["myproject"]  # Only search for imports under ./myproject
deps = ["pyproject.toml"]  # Only look for declared dependencies here
ignore_unused = ["black"]  # We use `black`, but we don't intend to import it
output_format = "human_detailed"  # Detailed report by default
```

Here is a complete list of configuration directives we support:

- `actions`: A list of one or more of these actions to perform: `list_imports`,
  `list_deps`, `check_undeclared`, `check_unused`. The default behavior
  corresponds to `actions = ["check_undeclared", "check_unused"]`.
- `code`: Files or directories containing the code to parse for import statements.
  Defaults to the current directory, i.e. like `code = ["."]`.
- `deps`: Files or directories containing the declared dependencies.
  Defaults to the current directory, i.e. like `deps = ["."]`.
- `pyenvs`: Python environments (directories like `.venv`, `__pypackages__`, or
  similar) to use for resolving project dependencies into provided import names.
  Defaults to an empty list, i.e. like `pyenvs = []`, which is interpreted as
  using the Python environment where FawltyDeps is installed (aka. `sys.path`).
- `output_format`: Which output format to use by default. One of `human_summary`,
  `human_detailed`, or `json`.
  The default corresponds to `output_format = "human_summary"`.
- `ignore_undeclared`: A list of specific dependencies to ignore when reporting
  undeclared dependencies, for example: `["some_module", "some_other_module"]`.
  The default is the empty list: `ignore_undeclared = []`.
- `ignore_unused`: A list of specific dependencies to ignore when reporting
  unused dependencies, for example: `["black", "mypy"]`.
  The default is the empty list: `ignore_unused = []`.
- `deps_parser_choice`: Manually select which format to use for parsing
  declared dependencies. Must be one of `"requirements.txt"`, `"setup.py"`,
  `"setup.cfg"`, `"pyproject.toml"`, or leave it unset (i.e. the default) for
  auto-detection (based on filename).
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

### Contributing more projects to the test suite

For bug reports, when a user reports that FawltyDeps does not work as it should
on their project, we aim to follow this process:

- If the project is freely available, we can add a relevant version of the
  project under `tests/real_projects`.
- We can then isolate the problems/issues/features and define/express them
  succinctly as one or more sample projects under `tests/sample_projects`.
- We examine the issue more closely and update core logic, adding/altering unit
  tests along the way.

The resulting updates are introduced to `fawltydeps` and reflected in our
expectations, first in the TOML for the sample project(s) and then finally in
the `real_projects` TOML.

If you find a project where FawltyDeps is not doing a good job, we appreciate
if you add that project under [`tests/real_projects`](./tests/real_projects).
To see how these tests work, look at the existing files in that directory.

## FAQ

### I run `fawltydeps` and get some undeclared dependencies. What can I do with it?

You can run a detailed report to see the exact location (file and line number), in which
the undeclared dependencies were imported:

```sh
fawltydeps --detailed
```

and debug each occurrence. Typically an undeclared dependency can be fixed in a couple of ways:

- A true undeclared dependency is fixed by _declaring_ it, e.g. adding it to your `pyproject.toml` or similar.
- If you disagree with FawltyDeps' classification, you can always use `--ignore-undeclared` to silence the error. If you're sure this dependency should not have been reported by FawltyDeps, you may consider filing a bug report.

### How not to display tools like `black` and `pylint` in _unused dependencies_?

By default, all packages declared as dependencies by your project are included
in the FawltyDeps analysis, even if they only contain tools that were not meant
to be `import`ed, but rather meant to be run by, say, in a pre-commit hook or a
CI script. In such cases you may use either:

```sh
fawltydeps --ignore-unused black pylint
```

or add an equivalent directive to the FawltyDeps configuration in your
`pyproject.toml` (see below).

### How can I store my `fawltydeps` command line options in a configuration file?

You can run:

```sh
fawltydeps --generate-toml-config
```

to generate a `[tool.fawltydeps]` section with the current configuration that
you can then directly copy into your `pyproject.toml`. Options that have their
default value are commented in this output, so you have quickly see where your
settings differ from the FawltyDeps defaults.

This also works together with other command line options, so for example in the
previous question, you could add `--generate-toml-config` to the command line
(i.e. run `fawltydeps --ignore-unused black pylint --generate-toml-config`),
to get this:

```toml
[tool.fawltydeps]
# Default options are commented...
ignore_unused = ["black", "pylint"]
```

### How to use FawltyDeps in a monorepo?

Running `fawltydeps` without arguments at the root of a monorepo
will most likely not give you a useful result:
it will collect dependencies and import statements from across the _entire_ monorepo.
The produced report may be overwhelming and at the same time not granular enough.

Instead, you should run FawltyDeps for each package separately.
This collects dependencies and import statements for one package at a time.

Having:

```sh
├ lib1
| ├ pyproject.toml
| ├ ....
├ lib2
| ├ pyproject.toml
| ├ ....
```

run for each `libX`:

```sh
fawltydeps libX
```

### Why must FawltyDeps run in the same Python environment as my project dependencies?

As explained above in the section on [resolving dependencies via your Python
environment](#resolving-dependencies-via-your-python-environment), the core
logic of FawltyDeps needs to match `import` statements in your code with
dependencies declared in your project configuration. This is straightforward
for many packages: for example you `pip install requests` and then
you can `import requests` in your code. However, this mapping from the name you
install to the name you `import` is not always self-evident:

- There are sometimes differences between the package name that you
  declare as a dependency, and the `import` name it provides. For example, you
  depend on `PyYAML`, but you `import yaml`.
- A dependency can expose more than one import name. For example the
  `setuptools` package exposes three `import`able packages: `_distutils_hack`,
  `pkg_resources`, and `setuptools`. So when you `import pkg_resources`,
  FawltyDeps need to figure out that this corresponds to the `setuptools`
  dependency.

To solve this, FawltyDeps looks at the packages installed in your current Python
environment (or the environment given by the `--pyenv` option) to correctly map
dependencies (package names) into the imports that they provide.

However, when an installed package is not found for a declared dependency, the
_identity mapping_ that FawltyDeps falls back to will still do a good job for
the majority of dependencies where the import name is indeed identical to the
package name that you depend on.

This is an area of active development in FawltyDeps, and we are
[working on better solutions](https://github.com/tweag/FawltyDeps/issues/195),
to avoid having to fall back to this identity mapping.

### Why does FawltyDeps fail to match `sklearn` with `scikit-learn`?

There are cases, where FawltyDeps may not match imports and obviously related
dependencies, like `sklearn` and `scikit-learn`. It will report `sklearn` as
_undeclared_ and `scikit-learn` as an _unused_ dependency.

This is very much related to the above question. `scikit-learn` is an example
of a package that exposes a different import name: `sklearn`.
When `scikit-learn` is not installed in the current Python environment (the one
that FawltyDeps uses to find these mappings), then FawltyDeps is unable to make
the connection between these two names.

To solve this problem, make sure that you either install and run FawltyDeps
in a development environment (e.g. virtualenv) where your project's dependencies
(including `scikit-learn`) are also installed. Alternatively, you can use the
`--pyenv` option to point at a Python environment where `scikit-learn` and your
other dependencies are installed.

### How can I pass Python code to FawltyDeps via standard input?

The `--code` argument accepts a single hyphen (`-`) as a special value meaning
that code should be read from standard input. When using this you may pipe or
redirect your Python code into FawltyDeps like this:

```sh
cat some/source/of/python/code | fawltydeps --code -
# or
fawltydeps --code - < some/source/of/python/code
```

You can also use this directly in the terminal to e.g. have FawltyDeps analyze
some Python code that is in your clipboard:

```sh
fawltydeps --code -
# FawltyDeps waits for code on stdin; paste from your clipboard,
# then press Ctrl+D to signal EOF (end-of-file).
```
