"""`canonical_url_key`: one key per article URL within a source (docs/architecture.md, data model).

Two URLs get the same key when they differ only by: scheme (http/https), host case, a leading
`www.`, a default port, a fragment, known tracking parameters, query parameter order, a trailing
slash, or percent-encoding (`%d9%85` vs `%D9%85` vs raw Arabic). Meaningful query parameters
are kept. The key identifies; it is not a URL to open (the article keeps its real URL).
"""

import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlsplit

TRACKING = re.compile(
    r"^(utm_\w+|fbclid|gclid|dclid|gbraid|wbraid|msclkid|yclid|mc_cid|mc_eid|igshid|_ga|_gl"
    r"|ref_src|cmpid|amp)$",
    re.IGNORECASE,
)
# Characters left unescaped in paths and query values (RFC 3986 unreserved + sub-delims).
_SAFE = "/:@!$&'()*+,;=-._~"


def canonical_url_key(url: str, base: str | None = None) -> str:
    parts = urlsplit(urljoin(base, url.strip()) if base else url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    if parts.port and parts.port not in (80, 443):
        host += f":{parts.port}"
    path = quote(unquote(parts.path), safe=_SAFE)
    if len(path) > 1:
        path = path.rstrip("/")
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not TRACKING.match(key)
    )
    key = f"https://{host}{path or '/'}"
    if query:
        key += "?" + urlencode(query, quote_via=quote, safe=_SAFE.replace("&", "").replace("=", ""))
    return key
