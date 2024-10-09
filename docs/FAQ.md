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

### Why must FawltyDeps run in the same Python environment as my project dependencies?

(This is no longer true since FawltyDeps v0.11: FawltyDeps should be able to
automatically find your project dependencies when they are installed in a Python
environment that exists within your project. If your project dependencies are
installed elsewhere, you can point FawltyDeps in their direction with `--pyenv`,
as explained above in the section on
[Python environment mapping](#python-environment-mapping))

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
dependency, the
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
When `scikit-learn` is not found in the Python environment(s) used by FawltyDeps,
then FawltyDeps is unable to make the connection between these two names.

To solve this problem, make sure that `scikit-learn` is installed in a Python
environment that belongs to your project. Alternatively, you can use the
`--pyenv` option to point at a Python environment where `scikit-learn` and your
other dependencies are installed.
