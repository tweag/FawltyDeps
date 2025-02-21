# Usage

To check the project in the current directory run:

```sh
fawltydeps
```

This will find imports in all the Python code under the current directory,
extract dependencies declared by your project, and then report
[_undeclared_ and _unused_ dependencies](explanation.md#key-concepts).

## Available Actions

FawltyDeps provides the following options for controlling what actions to perform. Only
one of these can be used at a time:

- `--check`: Report both undeclared and unused dependencies
- `--check-undeclared`: Report only undeclared dependencies
- `--check-unused`: Report only unused dependencies
- `--list-imports`: List third-party imports extracted from the project
- `--list-deps`: List declared dependencies extracted from the project
- `--list-sources`: List files/directories from which imports, declared
  dependencies and installed packages would be extracted

When none of these are specified, the default action is `--check`.

## Where to find code and dependency declarations

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

### Where to find Python code

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

At any time, if you want to see where FawltyDeps is looking for Python code,
you can use the `--list-sources --detailed` options.

### Where to find declared dependencies

The `--deps` option tells FawltyDeps where to look for your project's declared
dependencies. A number of file formats are supported:

- `*requirements*.txt` and `*requirements*.in`
- `pyproject.toml` (following PEP 621 or Poetry conventions)
- `setup.py` (only limited support for simple files with a single `setup()`
  call and no computation involved for setting the `install_requires` and
  `extras_require` arguments)
- `setup.cfg`
- `pixi.toml`
- `environment.yml`

The `--deps` option accepts a space-separated list of files or directories.
Each file will be parsed for declared dependencies; each directory will
be searched, parsing all of the supported files (see the above list) found
within. You would typically want to pass individual files, if you want to
be explicit about where to find the declared dependencies.

If no `--deps` option is passed, FawltyDeps will look for the above files under
the `basepath`, if given, or the current directory (i.e. same as `--deps .`).

### How to match `import` statements with declared dependencies 

When FawltyDeps analyzes undeclared and unused dependencies, it needs to match
`import` statements in your code with corresponding package dependencies
declared in your project configuration. We support the following options to help this process:

- `--pyenv`: Where to search for Python environments (e.g. virtualenvs) that have project dependencies installed. Finding installed dependencies is the best way to correctly match import names  and declared dependencies. If this is not given, the project directories will be searched for Python environments.
- `--custom-mapping-file`: A TOML file containing mapping of dependencies to import names defined by the user. When provided, this mapping takes precedence over looking through installed packages for a match. This is a power user feature for when you want full control of how FawltyDeps matches import names and package names.
- `--install-deps`: Allow FawltyDeps to auto-install declared dependencies into a separate temporary virtualenv to discover the imports they expose. This is potentially expensive, but it allows FawltyDeps to provide a good analysis when there is no existing Python environment with project dependencies installed.

For more details about the process of matching `import` statements to declared dependencies, please see the [Resolving dependencies section in Explanation](./explanation.md#resolving-dependencies).


## Excluding paths

If you want FawltyDeps to exclude parts of your source tree when loooking for
code, dependency declarations, or Python environments, then you can use the
`--exclude` option to specify path patterns to exclude, e.g. the following
command will skip everything under `tests/`:

```sh
fawltydeps --exclude tests/
```

The format of the exclude patterns is the same as used by `.gitignore` files,
[see here for a full description](https://git-scm.com/docs/gitignore#_pattern_format).

When the `--exclude` option is not specified, its default value is `".*"`, which
matches all paths that start with a dot (`.`), aka. "hidden" paths. In the above
example, if you want to exclude both hidden paths, and everything under
`tests/`, then instead use:

```sh
fawltydeps --exclude tests/ ".*"
```

(The extra quotes here are needed to prevent the shell from interpreting and
replacing the `*` wildcard.)

You can also point to exclude patterns stored in a file, with the
`--exclude-from` option. E.g. to read exclude patterns from `./my_excludes.txt`:

```sh
fawltydeps --exclude-from my_excludes.txt
```

Exclude patterns have lower priority than any paths you pass directly on the
command line, e.g. in this command:

```sh
fawltydeps --code my_file.py --exclude my_file.py
```

the `--code` options "wins" (i.e. imports in `my_file.py` will be found); the
`--exclude` option only takes affect when traversing directories to look for
more files. E.g. use this to find code inside `my_dir`, but skip Jupyter
notebooks:

```sh
fawltydeps --code my_dir --exclude "*.ipynb"
```

## Ignoring irrelevant results

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
We've introduced a `DEFAULT_IGNORE_UNUSED` list, which includes various
categories of commonly used development tools and dependencies.
FawltyDeps can automatically ignore these dependencies when checking for unused
imports. For the complete list, please see the `DEFAULT_IGNORE_UNUSED`
variable in the `fawltydeps/settings.py` file
in the repository. If you have additional dependencies that you want to exclude
from the check for unused imports, you can use the `--ignore-unused` option
to customize the ignore list. By providing your own list of dependencies with
this option, you can effectively overwrite the default list. For example:
`--ignore-unused black mypy some_other_module`

## Output formats

The default output from FawltyDeps is a summary outlining the relevant
dependencies found (according to the selected actions).
However you can also ask for more information from FawltyDeps:

- `--summary`: Default (human-readable) summary output
- `--detailed`: Longer (human-readable) output that includes the location of
  the relevant dependencies.
- `--json`: Verbose JSON-formatted output for other tools to consume and
  process further.

Only one of these options can be used at a time.

## More help

Run `fawltydeps --help` to get the full list of available options.
