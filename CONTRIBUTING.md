# Contributing

Thank you for your interest in contributing to FawltyDeps!
We welcome contributions from the community to help improve our project.
Please take a moment to review this guide before you get started.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
   - [Fork the Repository](#fork-the-repository)
   - [Clone the Repository](#clone-the-repository)
   - [Set Up Your Development Environment](#set-up-your-development-environment)
3. [Making Changes](#making-changes)
   - [Branch Naming](#branch-naming)
   - [Commit Messages](#commit-messages)
   - [Testing](#testing)
4. [Submitting Pull Requests](#submitting-pull-requests)
5. [Review Process](#review-process)

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
git clone https://github.com/tweag/FawltyDeps.git
```

### Set Up Your Development Environment

Follow the setup instructions in the project's [README](./README.md) to
configure your development environment.

## Making Changes

### Branch Naming

Create a new branch with a descriptive name for your feature or fix.

### Commit Messages

Write clear and concise commit messages that describe your changes.

### Testing

#### Running Tests Locally

For detailed instructions on running tests locally,
please refer to the [Nox section](#nox) in our [README](./README.md).

#### Continuous Integration

Every pull request you submit will trigger our continuous integration (CI) pipeline,
which includes running unit tests and integration tests using GitHub Actions.
Your changes must pass these tests before they can be merged.

Please make sure that your code changes do not break any existing tests,
and consider adding new tests when introducing new features or making significant modifications.

If you encounter any issues related to tests or need help with the testing process,
feel free to reach out in the pull request discussion.

## Submitting Pull Requests

When you're ready to submit your changes:

1. Push your changes to your forked repository:
   ```sh
   git push origin feature/your-feature-name
   ```
2. Visit the FawltyDeps repository on GitHub.
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
