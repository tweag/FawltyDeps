"Compare imports and dependencies"

from fawltydeps.dependencies import get_dependencies
from fawltydeps.extract_imports import parse_code


def compare_imports_dependencies() -> bool:
    """
    Compare import and dependencies according to chosen strategy
    """
    dependencies = get_dependencies()
    imports = parse_code("")
    return dependencies == imports
