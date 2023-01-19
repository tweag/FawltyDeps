"""Common utilities"""

import os
from pathlib import Path
from typing import Iterator


def walk_dir(path: Path) -> Iterator[Path]:
    """Walk a directory structure and yield Path objects for each file within.

    Wrapper around os.walk() that yields Path objects for files found (directly
    or transitively) under the given directory. Directories whose name start
    with a dot are skipped.
    """
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in files:
            yield Path(root, filename)
