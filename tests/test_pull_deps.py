"""Test the behavior of Analysis when requirements are pulled into a temp venv."""

from fawltydeps.main import Analysis
from fawltydeps.settings import Action, Settings


def test_analysis_on_a_simple_project(write_tmp_files):
    # create project
    project_dir = write_tmp_files(
        {
            "requirements.txt": """\
                pandas
                click
                """,
            "python_file.py": "import pandas, django",
        }
    )
    settings = Settings(
        actions={Action.REPORT_UNDECLARED, Action.REPORT_UNUSED},
        code=[project_dir],
        deps=[project_dir],
    )
    analysis = Analysis.create(settings)

    print("Verifying 'imports'...")
    actual_imports = {i.name for i in analysis.imports}
    expect_imports = set(["pandas", "django"])
    assert actual_imports == expect_imports

    print("Verifying 'dependencies'...")
    actual_declared = {d.name for d in analysis.declared_deps}
    expect_declared = set(["pandas", "click"])
    assert actual_declared == expect_declared

    print("Verifying 'undeclared_deps'...")
    actual_undeclared = {u.name for u in analysis.undeclared_deps}
    expect_undeclared = set(["django"])
    assert actual_undeclared == expect_undeclared

    print("Verifying 'unused_deps'...")
    actual_unused = {u.name for u in analysis.unused_deps}
    expect_unused = set(["click"])
    assert actual_unused == expect_unused
