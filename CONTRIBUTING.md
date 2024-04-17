# Contributing

Thank you for your interest in contributing to FawltyDeps!
We welcome contributions from the community to help improve our project.
Please take a moment to review this guide before you get started.

## Table of Contents

[Code of Conduct](#code-of-conduct)

[Getting Started](#getting-started)
   - [Fork the Repository](#fork-the-repository)
   - [Clone the Repository](#clone-the-repository)
   - [Set Up Your Development Environment](#set-up-your-development-environment)

[Making Changes](#making-changes)
   - [Branch Naming](#branch-naming)
   - [Commit Messages](#commit-messages)
   - [Testing](#testing)

[Submitting Pull Requests](#submitting-pull-requests)

[Review Process](#review-process)

## Code of Conduct

We expect all contributors to adhere to our [Code of Conduct](./CODE_OF_CONDUCT.md).
Please read it carefully before contributing.

## Getting Started

### Fork the Repository

If you haven't already, fork the [FawltyDeps repository](https://github.com/tweag/fawltydeps) on GitHub.
This will create a copy of the project in your GitHub account.

### Clone the Repository

Clone your fork of the repository to your local machine:

```sh
git clone git@github.com:<your_username>/FawltyDeps.git
```

### Set Up Your Development Environment

#### Poetry

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

#### Nox

We use [Nox](https://nox.thea.codes/en/stable/) for test/workflow automation:

```sh
nox --list        # List sessions
nox               # Run all available sessions
nox -R            # Run all available sessions, while reusing virtualenvs (i.e. faster)
nox -s tests      # Run unit tests on supported Python versions (that are available)
nox -s tests-3.7  # Run unit tests on Python v3.7 (assuming it is available locally)
nox -s integration_tests-3.11  # Run integration tests on Python 3.11
nox -s lint       # Run linters (mypy + ruff check) on all supported Python versions
nox -s format     # Check formatting (ruff format)
nox -s reformat   # Fix formatting (ruff format)
```

If you want to run a command individually, the corresponding session is defined inside
[`noxfile.py`](./noxfile.py). For example, these
commands will work:

```sh
pytest                   # Run unit tests
pytest -m integration    # Run integration tests
mypy                     # Run static type checking
ruff check .             # Run ruff linter
ruff format .            # Run ruff formatter
```

#### Shortcut: Nix

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

## Making Changes

### Branch Naming

Create a new branch with a descriptive name for your feature or fix.

### Commit Messages

Write clear and concise commit messages that describe your changes.

### Testing

#### Running Tests Locally

For detailed instructions on running tests locally, please refer to the Nox section in [Set Up Your Development Environment](#set-up-your-development-environment).

#### Integration tests

In addition to comprehensive unit tests under `tests/`, we also verify
FawltyDeps' behavior with integration tests which (among other things) include
testing with real-world projects. To that end, we have a framework in
[`tests/test_real_projects.py`](./tests/test_real_projects.py) for downloading
and unpacking tarballs of 3rd-party projects, and then running fawltydeps on them,
while verifying their output. These projects, along with the expected FawltyDeps
outputs, are defined in TOML files under
[`tests/real_projects`](./tests/real_projects).

#### Contributing more projects to the test suite

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

## Submitting Pull Requests

When you're ready to submit your changes:

1. Push your changes to your forked repository:
   ```sh
   git push origin feature/your-feature-name
   ```
2. Visit the [FawltyDeps repository](https://github.com/tweag/fawltydeps) on GitHub.
3. Click the "New Pull Request" button.
4. Select the appropriate branch and describe your changes in the pull request.
Be sure to reference any related issues.

## Review Process

Contributions to FawltyDeps go through a review process to ensure code quality
and alignment with project goals. Here's how the review process works:

1. **Submission:** When you submit a pull request (PR), our automated CI/CD
pipeline will run tests to check for issues and ensure that the code meets our coding standards.

2. **Code Review:** A maintainer or fellow contributor will review your PR.
They will provide feedback, suggest improvements, and ensure that the changes
align with the project's goals and coding guidelines.

3. **Discussion:** If changes or clarifications are needed, you may need to
engage in discussions with reviewers to address feedback and make necessary adjustments.

4. **Approval:** Once the PR meets all requirements and receives approval
from one or more maintainers or contributors, it will be labeled as "approved."

5. **Addressing Change Requests:** If a reviewer requests changes, please make
the necessary adjustments and commit the changes with a clear reference to the
reviewer's comment. Use the commit hash to indicate the changes you made. The
*reviewer* is responsible for resolving their comment once they are satisfied with
the changes.

6. **Merging:** A maintainer will merge the PR into the main branch. Please note
that only maintainers have merge permissions.

7. **Thank You!** Your contribution has now become a part of FawltyDeps. Thank you
for your contribution to the project!

We appreciate your contributions and value the effort you put into improving our project.
If you have any questions or need assistance during the review process, feel free
to ask in the PR discussion!
