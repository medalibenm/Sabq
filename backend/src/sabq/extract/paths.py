"""A small JSONPath subset for source configs: `$`, `.name`, `['name']`, `[0]`, `[*]`.

Examples: `$.title.rendered`, `$._embedded['wp:featuredmedia'][0].source_url`, `$[*]`.
Enough for every source so far, and strict: anything else is a config error.
"""

import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

_STEP = re.compile(
    r"""\.(?P<name>[A-Za-z_][A-Za-z0-9_-]*)
      | \[\s*(?P<quote>['"])(?P<key>.*?)(?P=quote)\s*\]
      | \[\s*(?P<index>-?\d+)\s*\]
      | \[\s*(?P<star>\*)\s*\]""",
    re.VERBOSE,
)

Step = str | int | None  # key, index, or None for [*]


@lru_cache(maxsize=1024)
def compile_path(path: str) -> tuple[Step, ...]:
    if not path.startswith("$"):
        raise ValueError(f"path must start with '$': {path!r}")
    steps: list[Step] = []
    pos = 1
    while pos < len(path):
        match = _STEP.match(path, pos)
        if match is None:
            raise ValueError(f"cannot read path {path!r} at position {pos}")
        if match["name"] is not None:
            steps.append(match["name"])
        elif match["quote"] is not None:
            steps.append(match["key"])
        elif match["index"] is not None:
            steps.append(int(match["index"]))
        else:
            steps.append(None)
        pos = match.end()
    return tuple(steps)


def find_all(data: Any, path: str) -> Iterator[Any]:
    """Every value the path reaches (missing keys and indexes are skipped, never an error)."""
    yield from _walk(data, compile_path(path))


def find_first(data: Any, path: str) -> Any:
    return next(find_all(data, path), None)


def _walk(node: Any, steps: tuple[Step, ...]) -> Iterator[Any]:
    if not steps:
        yield node
        return
    step, rest = steps[0], steps[1:]
    if step is None:
        if isinstance(node, dict):
            node = list(node.values())
        if isinstance(node, (list, tuple)):
            for child in node:
                yield from _walk(child, rest)
    elif isinstance(step, int):
        if isinstance(node, (list, tuple)) and -len(node) <= step < len(node):
            yield from _walk(node[step], rest)
    elif isinstance(node, dict) and step in node:
        yield from _walk(node[step], rest)
