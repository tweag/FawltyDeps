"Compare imports and dependencies"

from pathlib import Path
from fawltydeps.extract_dependencies import extract_dependencies
from fawltydeps.extract_imports import parse_code


def compare_imports_dependencies() -> bool:
    """
    Compare import and dependencies according to chosen strategy
    """
    dependencies = extract_dependencies(Path(""))
    imports = parse_code("")
    return dependencies == imports
