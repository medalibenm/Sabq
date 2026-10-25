"""Failed-login limiter, in memory (one app process; decision 2026-10-25).

After `max_failures` failed logins for an email, or from a client address, within `window_s`,
further attempts are refused until the oldest failure leaves the window. A success clears the
email's failures. A restart forgets everything, which is acceptable at this size.
"""

import time
from collections import deque
from collections.abc import Callable

MAX_KEYS = 10_000


class FailureLimiter:
    def __init__(
        self, max_failures: int, window_s: float, clock: Callable[[], float] = time.monotonic
    ):
        self.max_failures = max_failures
        self.window_s = window_s
        self.clock = clock
        self._failures: dict[str, deque[float]] = {}  # only keys with recent failures

    def blocked(self, *keys: str) -> bool:
        return any(self._count(key) >= self.max_failures for key in keys)

    def fail(self, *keys: str) -> None:
        moment = self.clock()
        if len(self._failures) > MAX_KEYS:  # many one-off emails: drop the expired ones
            for key in list(self._failures):
                self._count(key)
        for key in keys:
            self._count(key)
            self._failures.setdefault(key, deque()).append(moment)

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)

    def _count(self, key: str) -> int:
        failures = self._failures.get(key)
        if failures is None:
            return 0
        cutoff = self.clock() - self.window_s
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if not failures:
            del self._failures[key]
        return len(failures)
