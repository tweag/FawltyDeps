# How-to guides

## Ignore development tools

How not to display tools like `black` and `pylint` in _unused dependencies_?

By default, all packages declared as dependencies by your project are included
in the FawltyDeps analysis, even if they only contain tools that were not meant
to be `import`ed, but rather meant to be run by, say, in a pre-commit hook or a
CI script. In such cases you may use either:

```sh
fawltydeps --ignore-unused black pylint
```

or add an equivalent directive to the FawltyDeps configuration in your
`pyproject.toml` (see below).

## Store `fawltydeps` options in a configuration file.

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

## FawltyDeps with a monorepo.

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

## Passing Python code via standard input.

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

## Pre-commit hook

Assuming that you already use the [pre-commit](https://pre-commit.com)
tool, you can add something like this to your project's
`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/tweag/FawltyDeps
    rev: v0.17.0
    hooks:
      - id: check-undeclared
      - id: check-unused
```
