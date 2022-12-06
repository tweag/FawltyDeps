"Compare imports and dependencies"

from fawltydeps.dependencies import get_dependencies
from fawltydeps.parser import parse_imports


def compare_imports_dependencies():
    dependencies = get_dependencies()
    imports = parse_imports()
    pass
