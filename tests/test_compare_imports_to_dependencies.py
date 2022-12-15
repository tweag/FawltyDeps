"""Test the imports to dependencies comparison function."""

from fawltydeps.check import compare_imports_to_dependencies


def test_no_import_no_dependencies():
    imports = []
    dependencies = []
    expected = (set(), set())
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected


def test_stdlib_import_no_dependencies():
    imports = ["sys"]
    dependencies = []
    expected = (set(), set())
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected


def test_non_stdlib_import_no_dependencies():
    imports = ["pandas"]
    dependencies = []
    expected = (set(["pandas"]), set())
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected


def test_no_imports_one_dependency():
    imports = []
    dependencies = ["pandas"]
    expected = (set(), set(["pandas"]))
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected


def test_mixed_imports_non_stdlib_dependency():
    imports = ["sys", "pandas"]
    dependencies = ["pandas"]
    expected = (set(), set())
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected


def test_mixed_imports_no_dependencies():
    imports = ["sys", "pandas"]
    dependencies = []
    expected = (set(["pandas"]), set())
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected


def test_stdlib_import_and_non_stdlib_dependency():
    imports = ["sys"]
    dependencies = ["pandas"]
    expected = (set(), set(["pandas"]))
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected


def test_mixed_imports_with_unused_and_undeclared_dependencies():
    imports = ["sys", "pandas", "numpy"]
    dependencies = ["pandas", "scipy"]
    expected = (set(["numpy"]), set(["scipy"]))
    obtained = compare_imports_to_dependencies(imports, dependencies)
    assert obtained == expected
