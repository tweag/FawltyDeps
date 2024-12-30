# References

## Usage

To check the project in the current directory run:

```sh
fawltydeps
```

This will find imports in all the Python code under the current directory,
extract dependencies declared by your project, and then report
[_undeclared_ and _unused_ dependencies](explanation.md#key-concepts).

### Available Actions

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

At any time, if you want to see where FawltyDeps is looking for Python code,
you can use the `--list-sources --detailed` options.

#### Where to find declared dependencies

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
- `output_format`: Which output format to use by default. One of `human_summary`,
  `human_detailed`, or `json`.
  The default corresponds to `output_format = "human_summary"`.
- `code`: Files or directories containing the code to parse for import statements.
  Defaults to the current directory, i.e. like `code = ["."]`.
- `deps`: Files or directories containing the declared dependencies.
  Defaults to the current directory, i.e. like `deps = ["."]`.
- `pyenvs`: Where to look for Python environments (directories like `.venv`,
  `__pypackages__`, or similar) to be used for resolving project dependencies
  into provided import names. Defaults to looking for Python environments under
  the current directory, i.e. like `pyenvs = ["."]`.
- `ignore_undeclared`: A list of specific dependencies to ignore when reporting
  undeclared dependencies, for example: `["some_module", "some_other_module"]`.
  The default is the empty list: `ignore_undeclared = []`.
- `ignore_unused`: A list of specific dependencies to ignore when reporting
  unused dependencies, for example: `["black", "mypy", "some_other_module"]`.
  The default is a list including common development tools. However, you have the
  flexibility to overwrite this list according to your project's specific requirements.
  For the complete default list, please see the `DEFAULT_IGNORE_UNUSED`
  variable in the [`fawltydeps/settings.py`](https://github.com/tweag/FawltyDeps/blob/main/fawltydeps/settings.py) file
  in the repository.
- `deps_parser_choice`: Manually select which format to use for parsing
  declared dependencies. Must be one of `"requirements.txt"`, `"setup.py"`,
  `"setup.cfg"`, `"pyproject.toml"`, `"pixi.toml"`, `"environment.yml"`, or
  leave it unset (i.e. the default) for auto-detection (based on filename).
- `install-deps`: Automatically install Python dependencies gathered with
  FawltyDeps into a temporary virtual environment. This will use `uv` or `pip`
  to download and install packages from PyPI by default.
- `exclude`: File/directory patterns to exclude/ignore when looking for code
  (imports), dependency declarations and/or Python environments. Defaults to
  `exclude = [".*"]`, meaning that hidden/dot paths are excluded from traversal.
- `exclude_from`: Files (following the .gitignore format) containing exclude
  patterns to use when looking for code (imports), dependency declarations
  and/or Python environments. Defaults to an empty list: `exclude_from = []`.
- `verbosity`: An integer controlling the default log level of FawltyDeps:
  - `-2`: Only `CRITICAL`-level log messages are shown.
  - `-1`: `ERROR`-level log messages and above are shown.
  - `0`: `WARNING`-level log messages and above are shown. This is the default.
  - `1`: `INFO`-level log messages and above are shown.
  - `2`: All log messages (including `DEBUG`) are shown.
- `custom_mapping_file`: Paths to files containing user-defined mapping.
  Expected file format is defined in the User-defined mapping [section](explanation.md/#user-defined-mapping).
- `[tool.fawltydeps.custom_mapping]`: Section in the configuration, under which a custom mapping
  can be added. Expected format is described in the User-defined mapping [section](explanation.md/#user-defined-mapping).

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
- The ultimate defaults when no customizations takes place are hardcoded inside
  FawltyDeps, and are documented above.

### Excluding paths

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

## More help

Run `fawltydeps --help` to get the full list of available options.
