"""Entry-point module, to allow `python -m fawltydeps`."""

import sys

from fawltydeps.main import main

if __name__ == "__main__":
    sys.exit(main())
