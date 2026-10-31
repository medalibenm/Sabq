"""Source dates → aware UTC datetimes.

Accepted: ISO 8601 (`2026-10-17T14:07:54.254Z`, `2026-10-20T18:08:52+00:00`, naive
`2026-10-17T14:17:22`) and RFC 822 (`Sat, 17 Oct 2026 17:51:47 +0300`). A date with an offset
is converted; a naive date (or RFC 822 `-0000`, "zone unknown") is read in the source's
`published_tz` (Algerian sites: Africa/Algiers). The CMS behind El Khabar and El Moudjahid writes
`20:48 | 30-10-2026` in its feeds, always naive.
"""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo


def parse_date(value: object, naive_tz: str) -> datetime:
    text = str(value).strip()
    if not text:
        raise ValueError("empty date")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)  # naive for "-0000"
        except (TypeError, ValueError, IndexError):
            try:
                parsed = datetime.strptime(text, "%H:%M | %d-%m-%Y")
            except ValueError:
                raise ValueError(f"unrecognised date {text!r}") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(naive_tz))
    return parsed.astimezone(UTC)
