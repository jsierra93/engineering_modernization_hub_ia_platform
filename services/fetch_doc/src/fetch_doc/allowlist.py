"""Host allowlist for official documentation sources."""

from __future__ import annotations

ALLOWED_DOMAINS: frozenset[str] = frozenset(
    {
        "docs.pydantic.dev",
        "docs.python.org",
        "pypi.org",
        "osv.dev",
    }
)


def is_allowed_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    for domain in ALLOWED_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False
