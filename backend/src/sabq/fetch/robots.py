"""robots.txt rules for one origin (RFC 9309), parsed with protego.

How the response to `/robots.txt` is read (decision 2026-10-21):
  - 2xx: the rules apply (the most specific rule wins; a `SabqBot` group replaces `*`);
  - 401 / 403: everything is disallowed (the site is refusing us; we never work around it);
  - other 4xx (404, 410, ...): no robots.txt, everything is allowed;
  - 429, 5xx, network error: unreachable, so nothing is fetched until it can be read again.
"""

from dataclasses import dataclass
from typing import Literal

from protego import Protego

# RFC 9309: crawlers must parse at least 500 KiB; anything beyond is ignored.
MAX_ROBOTS_BYTES = 500 * 1024
AGENT_TOKEN = "SabqBot"

Verdict = Literal["rules", "allow_all", "disallow_all", "unreachable"]


@dataclass(frozen=True)
class RobotsRules:
    verdict: Verdict
    reason: str
    parser: Protego | None = None

    @classmethod
    def from_response(cls, status: int, body: bytes) -> "RobotsRules":
        if 200 <= status < 300:
            text = body[:MAX_ROBOTS_BYTES].decode("utf-8", errors="replace")
            return cls("rules", f"robots.txt {status}", Protego.parse(text))
        if status in (401, 403):
            return cls("disallow_all", f"robots.txt answered {status}")
        if 400 <= status < 500 and status != 429:
            return cls("allow_all", f"robots.txt answered {status} (none)")
        return cls("unreachable", f"robots.txt answered {status}")

    @classmethod
    def unreachable(cls, reason: str) -> "RobotsRules":
        return cls("unreachable", reason)

    def allows(self, url: str) -> bool:
        if self.verdict == "rules":
            return self.parser.can_fetch(url, AGENT_TOKEN)
        return self.verdict == "allow_all"

    @property
    def crawl_delay(self) -> float:
        if self.verdict == "rules":
            return float(self.parser.crawl_delay(AGENT_TOKEN) or 0)
        return 0.0
