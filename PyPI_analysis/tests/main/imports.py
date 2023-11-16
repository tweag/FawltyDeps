"""Example script that contains conditional, alternative, and dynamic imports patterns.
"""

import importlib
from importlib import import_module

import pytest

# Conditional imports

try:
    import conditional_1
except ImportError:
    pass

try:
    import conditional_2
except ModuleNotFoundError:
    pass

# Alternative imports

try:
    import alternative_primary_1
    from alternative_primary_2 import al2
except ImportError:
    import alternative_1


# Dynamic imports
x = importlib.import_module("dynamic_1")
y = import_module("dynamic_2")

importlib.import_module("dynamic_3")
import_module("dynamic_4")

pytest.importorskip("dynamic_pytest")
