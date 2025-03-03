[![PyPI Latest Release](https://img.shields.io/pypi/v/fawltydeps.svg)](https://pypi.org/project/fawltydeps/) [![Supported Python versions](https://img.shields.io/pypi/pyversions/fawltydeps.svg)](https://pypi.org/project/fawltydeps/) ![Build](https://img.shields.io/github/actions/workflow/status/tweag/fawltydeps/ci.yaml) [![Licence](https://img.shields.io/pypi/l/fawltydeps.svg)](https://pypi.org/project/fawltydeps/) [![Code of conduct](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](code_of_conduct.md) [![Discord channel](https://img.shields.io/discord/1174731094726295632)](https://discord.gg/V2d9xpgD4D)

# FawltyDeps

FawltyDeps is a dependency checker for Python that finds _undeclared_ and/or
_unused_ 3rd-party dependencies in your Python project.
The name is inspired by the Monty Python-adjacent
[Fawlty Towers](https://en.wikipedia.org/wiki/Fawlty_Towers) sitcom.

📝 Full documentation available at: [tweag.github.io/FawltyDeps](https://tweag.github.io/FawltyDeps/)

![FawltyDeps demo](https://github.com/tweag/FawltyDeps/raw/main/docs/images/fawltydeps_demo_tqdm.gif)

We [invite you](https://discord.gg/V2d9xpgD4D) to join our [Discord channel](https://discord.com/channels/1174731094726295632/1176462512212951090)! It's a great place to ask questions, share your ideas, and collaborate with other contributors.



## Key Concepts

- **_undeclared_ dependency**: a package that's used (in particular, `import`ed) by a project and which lacks a corresponding declaration to ensure that it's available.
  For example, you `import numpy`, but you've forgotten to include `numpy` in your `requirements.txt`.
  Pragmatically, this means the project is prone to runtime errors.
- **_unused_ dependency**: a package that's declared as necessary for a project but which is never used by project code.
  For example, you have `numpy` listed in your `requirements.txt`, but you never actually `import numpy`.
  Pragmatically, this means that project installation may consume more space than needed and will be more likely to break with future software releases; in short, these are costs paid for no benefit.

Your project dependencies may look like this:


<p align="center">
  <img src="docs/images/fd_dependencies.png" width="800px" style="max-width: 800px; height: auto;">
</p>

But FawltyDeps is all about helping you get to this perfect green spot:

<p align="center">
  <img src="docs/images/fd_dependencies_ideal.png" width="400px" style="max-width: 400px; height: auto;">
</p>

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


## Development

For details on setting up your development environment, please refer to the
contributing guidelines of how to [set up your development environment](./CONTRIBUTING.md#set-up-your-development-environment)
in our [CONTRIBUTING.md](CONTRIBUTING.md) file.

## Integration tests

For details on integration tests, please refer to the
[Testing section](./CONTRIBUTING.md#testing) in our [CONTRIBUTING.md](./CONTRIBUTING.md) file.

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

### Does FawltyDeps need to run in the same Python environment as my project?

No (not since FawltyDeps v0.11). FawltyDeps should be able to automatically find
your project dependencies when they are installed in a Python environment that
exists within your project. If your project dependencies are installed
elsewhere, you can point FawltyDeps in their direction with `--pyenv`, as
explained above in the section on
[Python environment mapping](#python-environment-mapping)).

See also the next question for more details.

### Why does FawltyDeps need a Python environment with my project dependencies?

The reason why FawltyDeps need to find your project dependencies _somewhere_ is
that the core logic of FawltyDeps needs to match `import` statements in your
code with dependencies declared in your project configuration. This seems
straightforward for many packages: for example you `pip install requests` and
then you can `import requests` in your code. However, this mapping from the name
you install to the name you `import` is not always self-evident:

- There are sometimes differences between the package name that you
  declare as a dependency, and the `import` name it provides. For example, you
  depend on `PyYAML`, but you `import yaml`.
- A dependency can expose more than one import name. For example the
  `setuptools` package exposes three `import`able packages: `_distutils_hack`,
  `pkg_resources`, and `setuptools`. So when you `import pkg_resources`,
  FawltyDeps need to figure out that this corresponds to the `setuptools`
  dependency.

To solve this, FawltyDeps looks at the packages installed in your Python
environment to correctly map dependencies (package names) into the imports that
they provide. This is:

- any Python environment found via the `--pyenv` option,
- or if `--pyenv` is not given: any Python environment found within your
  project (`basepath` or the current directory).
- In addition, FawltyDeps will use the _current Python environment_,
  i.e. the one in which FawltyDeps itself is running.

As a final resort, when an installed package is not found for a declared
dependency, the _identity mapping_ that FawltyDeps falls back to will still do
a good job for the majority of dependencies where the import name is indeed
identical to the package name that you depend on.

### My project is using Python version before v3.8, can I still use FawltyDeps?

Yes! Even though FawltyDeps itself runs on Python >=v3.8, we try to support
analyzing projects that run on any version of Python 3.

As explained in the previous two questions, FawltyDeps itself does not need to
run inside the same Python environment as your project and its dependencies.

You can instead install FawltyDeps using a newer Python version (e.g. via
[uvx](https://docs.astral.sh/uv/guides/tools/#running-tools) or
[pipx](https://github.com/pypa/pipx)). Then run FawltyDeps from inside your
project directory. If your project has an embedded Python environment (e.g.
under `.venv/`) then FawltyDeps should automatically find it and use it to
analyze your project dependencies. Alternatively, you can always use `--pyenv`
to point FawltyDeps to where your dependencies are installed.

Currently the lowest Python version that your project can use (and still be
analyzed by FawltyDeps) is determined by our use of the
[`ast` module](https://docs.python.org/3/library/ast.html#module-ast) in the
Python standard library: As long as your project's Python syntax is compatible
with the Python version that FawltyDeps runs on, you should be fine. If you run
into problems with older Python syntax (e.g. using `async` or `await` as
variable names), please open an issue, and we'll look into extending our
support further.

A final resort can be to downgrade to an older version of FawltyDeps that is
compatible with the Python version used in your project. Currently, the only
Python version we have dropped support for is v3.7, and FawltyDeps v0.18 is
the last release to support this Python version.

### Why does FawltyDeps fail to match `sklearn` with `scikit-learn`?

There are cases, where FawltyDeps may not match imports and obviously related
dependencies, like `sklearn` and `scikit-learn`. It will report `sklearn` as
_undeclared_ and `scikit-learn` as an _unused_ dependency.

This is very much related to the above question. `scikit-learn` is an example
of a package that exposes a different import name: `sklearn`.
When `scikit-learn` is not found in the Python environment(s) used by FawltyDeps,
then FawltyDeps is unable to make the connection between these two names.

To solve this problem, make sure that `scikit-learn` is installed in a Python
environment that belongs to your project. Alternatively, you can use the
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

### Can I use FawltyDeps as a pre-commit hook?

Yes! Assuming that you already use the [pre-commit](https://pre-commit.com)
tool, you can add something like this to your project's
`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/tweag/FawltyDeps
    rev: v0.18.0
    hooks:
      - id: check-undeclared
      - id: check-unused
```


### Can I use FawltyDeps in continuous integration?

Yes! This works well when run as a lint step in continuous integration systems.

Please see [tweag/FawltyDeps-action](https://github.com/tweag/FawltyDeps-action) for a GitHub Action that implements FawltyDeps linting. You can also get the FawltyDeps GitHub Action from the [Actions Marketplace](https://github.com/marketplace/actions/fawltydeps).
