# FawltyDeps

FawltyDeps is a dependency checker for Python that finds _undeclared_ and/or _unused_ 3rd-party
dependencies in your Python project. For example, it will find modules that you are `import`ing in
your code, but have forgotten to declare in your `pyproject.toml` or `requirements.txt`.

![FawltyDeps demo](images/fawltydeps_demo_tqdm.gif)

## Features

- Finds undeclared dependencies: modules you are `import`ing, but forgot to declare as dependencies.
- Finds unused dependencies: dependencies you declared, but never `import`.
- Supports Python code in regular files and Jupyter notebooks.
- Supports many dependency declaration formats: `pyproject.toml`, `requirements.txt`, `setup.py`,
  `setup.cfg`, `environment.yml`, and `pixi.toml`.
- Can be installed into your project as a development dependency, or run as an independent tool.
- Easily automated, e.g. as a pre-commit hook or as a CI action.

## Why FawltyDeps?

Good dependency management is crucial for maintaining a healthy codebase and avoiding the
"Works on my machine" problem. Over time, unused dependencies can accumulate, leading to
bloated environments, longer installation times, and potential security risks. FawltyDeps helps
keep your project installable, lean and efficient.

We [invite you](https://discord.gg/V2d9xpgD4D) to join our [Discord channel](https://discord.com/channels/1174731094726295632/1176462512212951090)!
It's a great place to ask questions, share your ideas, and collaborate with other users and contributors.
