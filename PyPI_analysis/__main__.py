"""Entry-point module, to allow `python -m fawltydeps`."""

import sys

from PyPI_analysis.main import main

if __name__ == "__main__":
    sys.exit(main())
