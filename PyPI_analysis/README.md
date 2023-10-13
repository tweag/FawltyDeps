# PyPI analysis

This directory contains the code for automating PyPI analysis. It is a command-line tool designed to facilitate pre-analysis of Python code and detect conditional, alternative, or dynamic imports. Much of the code is reused from the main Fawltydeps source code.

## Usage
To use PyPI Analysis, follow these steps:

1. Install Poetry, and then run:
```
poetry install
```
to create a virtualenv with all  dependencies installed.

2. Activate the Virtual Environment

After installing Poetry, activate the virtual environment using:
```
poetry shell
```
to jump into a development shell with this virtualenv activated.

3. Perform the Analysis

In the Poetry shell, navigate to the directory you want to analyze and execute the following command:
```
python3 -m PyPI_analysis
```
This will initiate the analysis and report any conditional, alternative, or dynamic imports detected in the code.

To learn more about the available options:
```
python3 -m PyPI_analysis --help
```
