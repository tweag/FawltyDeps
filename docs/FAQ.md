## When do I need to use `--base-dir`?

When FawltyDeps analyzes `import` statements in your code, it needs to correctly
differentiate between 1st-party imports (i.e. modules that are found inside your
project) and 3rd-party imports (and that indicate real 3rd-party dependencies).
FawltyDeps needs a base directory where it can find these 1st-party imports, and
by default it uses directory information passed on the command line.
For example:

- `fawltydeps my_project/` will look for Python code under `my_project/`, and
  will also use `my_project/` as the base directory for 1st-party imports.
- Likewise, `fawltydeps --code=my_project/` will do the same.
- `fawltydeps --code=projectA/ --code=projectB/` will use `projectA/` as the
  base directory for code under `projectA/`, and `projectB/` as the
  base directory for code under `projectB/`.
- If you pass only filenames, no directories, e.g.
  `fawltydeps foo/main.py lib/bar.py`, then FawltyDeps will default to using the
  current directory (`./`) as the base directory. This is fine as long as the
  current directory is an appropriate base directory for your project, for
  example when `foo/main.py` imports `lib/bar.py` with a statement like
  `from lib import bar`.

There are some scenarios, however, where the base directory is not correctly
deduced by FawltyDeps, and where you would use `--base-dir` to adjust this
(and without otherwise changing what code FawltyDeps is looking at).

- If you only pass filenames, no directories, and the current directory is _not_
  an appropriate base directory. In the above filename-only example, if
  `foo/main.py` instead uses `import bar` (say your project is run in a manner
  where `lib/` is on the `$PYTHONPATH`), then this `bar` import will not be
  found in the current directory, and you would need to pass `--base-dir=lib/`
  in order to bring FawltyDeps up to speed.
- If your project structure is more complex -- e.g. if you are running
  FawltyDeps on a subproject + libs within a larger monorepo, and you need to
  identify which directory is the appropriate base for imports, e.g.
  `fawltydeps subproject/main/ subproject/lib/ --base-dir=subproject/`

Note that `--base-dir` changes the base directory for _all_ code that is
analyzed by FawltyDeps. For example, when you run
`fawltydeps --code=my_project/ --code=other_file.py --base-dir=lib/`, both the
code found under `my_project/` and the code in `other_file.py` will be analyzed
with the assumption that 1st-party imports will be found under `lib/`.
(Without `--base-dir`, the implicit base directories would be `my_project/` for
code found under there, and `./` for code in `other_file.py`.)

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
