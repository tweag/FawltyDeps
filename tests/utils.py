""" Utilities to share among test modules """

import io
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fawltydeps.main import main
from fawltydeps.packages import DependenciesMapping, Package
from fawltydeps.types import (
    DeclaredDependency,
    Location,
    ParsedImport,
    UndeclaredDependency,
    UnusedDependency,
)

SAMPLE_PROJECTS_DIR = Path(__file__).with_name("sample_projects")

logger = logging.getLogger(__name__)


def assert_unordered_equivalence(actual: Iterable[Any], expected: Iterable[Any]):
    assert sorted(actual) == sorted(expected)


def collect_dep_names(deps: Iterable[DeclaredDependency]) -> Iterable[str]:
    return (dep.name for dep in deps)


def imports_factory(*imports: str) -> List[ParsedImport]:
    return [ParsedImport(imp, Location("<stdin>")) for imp in imports]


def deps_factory(*deps: str, path: str = "foo") -> List[DeclaredDependency]:
    "Dependency generator with a common path for all dependencies"
    return [DeclaredDependency(name=dep, source=Location(Path(path))) for dep in deps]


# There are the packages/imports we expect to be able to resolve via the default
# LocalPackageResolver. See the isolate_default_resolver() fixture for how we
# make this come true.
default_sys_path_env_for_tests = {
    "pip": {"pip"},
    "setuptools": {"setuptools", "pkg_resources", "_distutils_hack"},
    "isort": {"isort"},
    "typing-extensions": {"typing_extensions"},
}


def resolved_factory(*deps: str) -> Dict[str, Package]:
    def make_package(dep: str) -> Package:
        imports = default_sys_path_env_for_tests.get(dep, None)
        if imports is not None:  # exists in local env
            return Package(dep, {DependenciesMapping.LOCAL_ENV: imports})
        # fall back to identity mapping
        return Package(dep, {DependenciesMapping.IDENTITY: {dep}})

    return {dep: make_package(dep) for dep in deps}


def undeclared_factory(*deps: str) -> List[UndeclaredDependency]:
    return [UndeclaredDependency(dep, [Location("<stdin>")]) for dep in deps]


def unused_factory(*deps: str) -> List[UnusedDependency]:
    return [UnusedDependency(dep, [Location(Path("foo"))]) for dep in deps]


def run_fawltydeps_subprocess(
    *args: str,
    config_file: Path = Path("/dev/null"),
    to_stdin: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Tuple[str, str, int]:
    """Run FawltyDeps as a subprocess. Designed for integration tests."""
    proc = subprocess.run(
        ["fawltydeps", f"--config-file={config_file}"] + list(args),
        input=to_stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        cwd=cwd,
    )
    logger.debug(
        f"Run `fawltydeps {' '.join(args)}` returned exit code {proc.returncode}\n"
        f"    ---- STDOUT ----\n{proc.stdout}"
        f"    ---- STDERR ----\n{proc.stderr}"
        "    ----------------"
    )
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


def run_fawltydeps_function(
    *args: str,
    config_file: Path = Path("/dev/null"),
    to_stdin: Optional[str] = None,
    basepath: Optional[Path] = None,
) -> Tuple[str, int]:
    """Run FawltyDeps with `main` function. Designed for unit tests.

    Ignores logging output and returns stdout and the exit code
    """
    output = io.StringIO()
    exit_code = main(
        cmdline_args=([str(basepath)] if basepath else [])
        + [f"--config-file={str(config_file)}"]
        + list(args),
        stdin=io.StringIO(to_stdin),
        stdout=output,
    )

    output_value = output.getvalue()
    logger.debug(
        f"Run `fawltydeps {' '.join(args)}` returned exit code {exit_code}\n"
        f"    ---- STDOUT ----\n{output_value}"
        "    ----------------"
    )
    output.close()
    return output_value.strip(), exit_code


@dataclass
class FDTestVector:  # pylint: disable=too-many-instance-attributes
    """Test vectors for various parts of the FawltyDeps core logic."""

    id: str
    imports: List[ParsedImport] = field(default_factory=list)
    declared_deps: List[DeclaredDependency] = field(default_factory=list)
    ignore_unused: List[str] = field(default_factory=list)
    ignore_undeclared: List[str] = field(default_factory=list)
    expect_resolved_deps: Dict[str, Package] = field(default_factory=dict)
    expect_undeclared_deps: List[UndeclaredDependency] = field(default_factory=list)
    expect_unused_deps: List[UnusedDependency] = field(default_factory=list)


test_vectors = [
    FDTestVector("no_imports_no_deps"),
    FDTestVector(
        "one_import_no_deps",
        imports=imports_factory("pandas"),
        expect_undeclared_deps=undeclared_factory("pandas"),
    ),
    FDTestVector(
        "no_imports_one_dep",
        declared_deps=deps_factory("pandas"),
        expect_resolved_deps=resolved_factory("pandas"),
        expect_unused_deps=unused_factory("pandas"),
    ),
    FDTestVector(
        "matched_import_with_dep",
        imports=imports_factory("pandas"),
        declared_deps=deps_factory("pandas"),
        expect_resolved_deps=resolved_factory("pandas"),
    ),
    FDTestVector(
        "mixed_imports_with_unused_and_undeclared_deps",
        imports=imports_factory("pandas", "numpy"),
        declared_deps=deps_factory("pandas", "scipy"),
        expect_resolved_deps=resolved_factory("pandas", "scipy"),
        expect_undeclared_deps=undeclared_factory("numpy"),
        expect_unused_deps=unused_factory("scipy"),
    ),
    FDTestVector(
        "mixed_imports_from_diff_files_with_unused_and_undeclared_deps",
        imports=imports_factory("pandas")
        + [ParsedImport("numpy", Location(Path("my_file.py"), lineno=3))],
        declared_deps=deps_factory("pandas", "scipy"),
        expect_resolved_deps=resolved_factory("pandas", "scipy"),
        expect_undeclared_deps=[
            UndeclaredDependency(
                "numpy",
                [Location(Path("my_file.py"), lineno=3)],
            )
        ],
        expect_unused_deps=unused_factory("scipy"),
    ),
    FDTestVector(
        "unused_dep_that_is_ignore_unused__not_reported_as_unused",
        declared_deps=deps_factory("pip"),
        ignore_unused=["pip"],
        expect_resolved_deps=resolved_factory("pip"),
    ),
    FDTestVector(
        "used_dep_that_is_ignore_unused__not_reported_as_unused",
        imports=imports_factory("isort"),
        declared_deps=deps_factory("isort"),
        ignore_unused=["isort"],
        expect_resolved_deps=resolved_factory("isort"),
    ),
    FDTestVector(
        "undeclared_dep_that_is_ignore_unused__reported_as_undeclared",
        imports=imports_factory("isort"),
        ignore_unused=["isort"],
        expect_undeclared_deps=undeclared_factory("isort"),
    ),
    FDTestVector(
        "mixed_deps__report_undeclared_and_non_ignored_unused",
        imports=imports_factory("pandas", "numpy"),
        declared_deps=deps_factory("pandas", "isort", "flake8"),
        ignore_unused=["isort"],
        expect_resolved_deps=resolved_factory("pandas", "isort", "flake8"),
        expect_undeclared_deps=undeclared_factory("numpy"),
        expect_unused_deps=unused_factory("flake8"),
    ),
    FDTestVector(
        "undeclared_dep_that_is_ignore_undeclared__not_reported_as_undeclared",
        imports=imports_factory("invalid_import"),
        ignore_undeclared=["invalid_import"],
    ),
    FDTestVector(
        "declared_dep_that_is_ignore_undeclared__not_reported_as_undeclared",
        imports=imports_factory("isort"),
        declared_deps=deps_factory("isort"),
        ignore_undeclared=["isort"],
        expect_resolved_deps=resolved_factory("isort"),
    ),
    FDTestVector(
        "unused_dep_that_is_ignore_undeclared__reported_as_unused",
        declared_deps=deps_factory("isort"),
        ignore_undeclared=["isort"],
        expect_resolved_deps=resolved_factory("isort"),
        expect_unused_deps=unused_factory("isort"),
    ),
    FDTestVector(
        "mixed_deps__report_unused_and_non_ignored_undeclared",
        imports=imports_factory("pandas", "numpy", "not_valid"),
        declared_deps=deps_factory("pandas", "flake8"),
        ignore_undeclared=["not_valid"],
        expect_resolved_deps=resolved_factory("pandas", "flake8"),
        expect_undeclared_deps=undeclared_factory("numpy"),
        expect_unused_deps=unused_factory("flake8"),
    ),
    FDTestVector(
        "mixed_deps__report_only_non_ignored_unused_and_non_ignored_undeclared",
        imports=imports_factory("pandas", "numpy", "not_valid"),
        declared_deps=deps_factory("pandas", "flake8", "isort"),
        ignore_undeclared=["not_valid"],
        ignore_unused=["isort"],
        expect_resolved_deps=resolved_factory("pandas", "flake8", "isort"),
        expect_undeclared_deps=undeclared_factory("numpy"),
        expect_unused_deps=unused_factory("flake8"),
    ),
    FDTestVector(
        "deps_with_diff_name_for_the_same_import",
        declared_deps=[
            DeclaredDependency(name="Pip", source=Location(Path("requirements1.txt"))),
            DeclaredDependency(name="pip", source=Location(Path("requirements2.txt"))),
        ],
        expect_resolved_deps={
            "Pip": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
            "pip": Package("pip", {DependenciesMapping.LOCAL_ENV: {"pip"}}),
        },
        expect_unused_deps=[
            UnusedDependency("Pip", [Location(Path("requirements1.txt"))]),
            UnusedDependency("pip", [Location(Path("requirements2.txt"))]),
        ],
    ),
]
