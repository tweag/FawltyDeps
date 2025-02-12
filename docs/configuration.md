# Configuration

## Configuration file

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

## Environment variables

In addition to configuring FawltyDeps via `pyproject.toml` as show above, you
may also pass the above configuration directives via the environment, using a
`fawltydeps_` prefix. For example, to enable JSON output via the environment,
set `fawltydeps_output_format=json` in FawltyDeps' environment.

## Configuration cascade

- Command-line options take precedence, and override corresponding settings
  passed via the environment or `pyproject.toml`.
- Environment variables override corresponding settings from `pyproject.toml`.
- Configuration in `pyproject.toml` override only the ultimate hardcoded defaults.
- The ultimate defaults when no customizations takes place are hardcoded inside
  FawltyDeps, and are documented above.

