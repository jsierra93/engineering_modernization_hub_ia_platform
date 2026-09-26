"""Lambda handler for `fetch_doc` (PLAN.md task 3.6).

Lets `agent_phase` consult official documentation while planning a
modernization, restricted to an allowlist of domains (`fetch_doc.
allowlist`). This service gets **zero AWS permissions, ever** (CLAUDE.md's
permissions table, PLAN.md 3.6-tf) -- no boto3 import, no AWS resource
reference, anywhere in this package.

Follows the same injectable-HTTP-session pattern as
`services/fetch_repo/src/fetch_repo/handler.py`: a pure function
(`fetch_document`) takes an injected session so it's fully testable with
`responses`, and `handler()` is the thin Lambda entrypoint that
constructs the real `requests.Session()`.

Per CLAUDE.md invariant #9 ("external content is untrusted... enters the
prompt inside explicit delimiters, marked as data, never as
instructions"), this module returns a plain string plus a small amount
of provenance metadata -- never anything shaped like trusted framework
output. Wrapping it in delimiters before it reaches a prompt is
`agent_phase`'s job, not this one's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from fetch_doc.allowlist import is_allowed_host

# A documentation page is HTML/text, not a binary artifact -- a few MB is
# already generous for one page. Chosen the same way fetch_repo's size
# caps are chosen (sanitize.py): a round, defensible number, not tuned to
# any specific page. Anything past this is treated as suspicious in the
# same category `fetch_repo` treats an oversized tarball, not merely
# "big".
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB

# Generous enough for a slow doc site, short enough that a hung/adversarial
# host can't stall the agent's planning phase indefinitely.
REQUEST_TIMEOUT_SECONDS = 15


class FetchDocError(Exception):
    """Base class for every reason `fetch_document` refuses or fails a
    request. Callers (ultimately the policy gate / agent_phase) should
    treat any of these as "this source could not be used", never as a
    successful empty fetch."""


class DisallowedSchemeError(FetchDocError):
    """Raised when the URL isn't HTTPS."""


class DisallowedHostError(FetchDocError):
    """Raised when the URL's host isn't on the allowlist (see
    `fetch_doc.allowlist.is_allowed_host` for the exact boundary rule)."""


class ResponseTooLargeError(FetchDocError):
    """Raised when the response exceeds `MAX_RESPONSE_BYTES`, either via
    `Content-Length` or by the actual body read."""


class HttpGetError(FetchDocError):
    """Raised when the request itself fails (network error, non-2xx
    status) -- distinct from the above so callers can tell "blocked by
    policy" apart from "the source was unreachable"."""


class SupportsGet(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class DocumentResult:
    """Untrusted content plus provenance. `content` is a plain string --
    never something that could be mistaken for trusted framework output.
    The caller (agent_phase) is responsible for delimiting it before it
    reaches a prompt, per CLAUDE.md invariant #9."""

    url: str
    host: str
    content: str
    content_type: str | None


def _validate_url(url: str) -> str:
    """Returns the URL's lowercased host if it passes scheme + allowlist
    checks, else raises. Kept as its own step so both checks happen
    *before* any network call -- an SSRF-style probe against a
    disallowed host should never even open a connection."""

    parts = urlsplit(url)

    if parts.scheme != "https":
        raise DisallowedSchemeError(f"rejected {url!r}: only https:// URLs are allowed")

    host = (parts.hostname or "").lower()
    if not host or not is_allowed_host(host):
        raise DisallowedHostError(f"rejected {url!r}: host {host!r} is not on the allowlist")

    return host


def fetch_document(url: str, http_session: SupportsGet) -> DocumentResult:
    """Fetch `url` via the injected HTTP session, after validating it's
    HTTPS and its host is allowlisted.

    Raises `DisallowedSchemeError` / `DisallowedHostError` without making
    any request at all -- the allowlist check happens first, on purpose,
    so a rejected URL never reaches the network. Raises
    `ResponseTooLargeError` if the response is (or claims to be) larger
    than `MAX_RESPONSE_BYTES`, and `HttpGetError` for any other request
    failure.
    """

    host = _validate_url(url)

    try:
        response = http_session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except FetchDocError:
        raise
    except Exception as exc:  # noqa: BLE001 - re-raised as our own type
        raise HttpGetError(f"failed to fetch {url}: {exc}") from exc

    content_length = response.headers.get("Content-Length") if hasattr(response, "headers") else None
    if content_length is not None:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise ResponseTooLargeError(
                    f"rejected {url!r}: Content-Length {content_length} exceeds "
                    f"the {MAX_RESPONSE_BYTES}-byte limit"
                )
        except ValueError:
            pass  # malformed header -- fall through to the actual-size check below

    body = response.content
    if len(body) > MAX_RESPONSE_BYTES:
        raise ResponseTooLargeError(
            f"rejected {url!r}: response body of {len(body)} bytes exceeds "
            f"the {MAX_RESPONSE_BYTES}-byte limit"
        )

    encoding = getattr(response, "encoding", None) or "utf-8"
    try:
        text = body.decode(encoding, errors="replace")
    except (LookupError, TypeError):
        text = body.decode("utf-8", errors="replace")

    content_type = None
    if hasattr(response, "headers"):
        content_type = response.headers.get("Content-Type")

    return DocumentResult(url=url, host=host, content=text, content_type=content_type)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Step Functions / tool-call entrypoint. Expected input:
    `{"url": ...}`. Constructs the real `requests.Session()`; tests call
    `fetch_document` directly with an injected fake (see
    `services/fetch_repo`'s handler for the identical pattern).

    Deliberately imports `requests` only, never `boto3` -- this service
    has zero AWS permissions (CLAUDE.md's permissions table) and that
    must hold even at the import level, not just in the IAM role.
    """

    import requests

    result = fetch_document(url=event["url"], http_session=requests.Session())
    return {
        "url": result.url,
        "host": result.host,
        "content": result.content,
        "content_type": result.content_type,
    }
