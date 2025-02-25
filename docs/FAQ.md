## Why does FawltyDeps fail to match `sklearn` with `scikit-learn`?

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


## My project is using Python version before v3.9, can I still use FawltyDeps?

Yes! Even though FawltyDeps itself runs on Python >=v3.9, we try to support
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
compatible with the Python version used in your project. Currently, these are
the Python versions we have dropped support for, and the latest FawltyDeps
release to support that version:

- Python v3.7 last supported in FawltyDeps v0.18.
- Python v3.8 last supported in FawltyDeps v0.19.


## Does FawltyDeps need to run in the same Python environment as my project?

No (not since FawltyDeps v0.11). FawltyDeps should be able to automatically find
your project dependencies when they are installed in a Python environment that
exists within your project. If your project dependencies are installed
elsewhere, you can point FawltyDeps in their direction with `--pyenv`, as
explained in the section on
[Python environment mapping](explanation.md/#local-python-environment-mapping).

See also the next question for more details.


## Why does FawltyDeps need a Python environment with my project dependencies?

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
