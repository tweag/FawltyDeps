"Parse imports from the source code"

from typing import Iterator


def parse_imports(code: str) -> Iterator[str]:
    yield "foo"
