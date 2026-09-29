"""Fetches an allowlisted HTTPS document and returns its text as untrusted content.
No boto3 import: this service holds no AWS permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import urlsplit

from fetch_doc.allowlist import is_allowed_host

MAX_RESPONSE_BYTES = 5 * 1024 * 1024

REQUEST_TIMEOUT_SECONDS = 15

MAX_TEXT_CHARS = 20_000

_SKIPPED_ELEMENTS = {"script", "style", "noscript", "svg", "head", "nav", "footer"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _SKIPPED_ELEMENTS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_ELEMENTS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    @property
    def text(self) -> str:
        return "\n".join(self._chunks)


def extract_text(content: str, content_type: str | None) -> str:
    if content_type and "html" not in content_type.lower():
        return content
    parser = _TextExtractor()
    try:
        parser.feed(content)
    except Exception:  # noqa: BLE001 - malformed markup is not a fetch failure
        return content
    return parser.text or content


class FetchDocError(Exception):
    pass


class DisallowedSchemeError(FetchDocError):
    pass


class DisallowedHostError(FetchDocError):
    pass


class ResponseTooLargeError(FetchDocError):
    pass


class HttpGetError(FetchDocError):
    pass


class SupportsGet(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class DocumentResult:
    url: str
    host: str
    content: str
    content_type: str | None


def _validate_url(url: str) -> str:
    parts = urlsplit(url)

    if parts.scheme != "https":
        raise DisallowedSchemeError(f"rejected {url!r}: only https:// URLs are allowed")

    host = (parts.hostname or "").lower()
    if not host or not is_allowed_host(host):
        raise DisallowedHostError(f"rejected {url!r}: host {host!r} is not on the allowlist")

    return host


def fetch_document(url: str, http_session: SupportsGet) -> DocumentResult:
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
            pass

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

    text = extract_text(text, content_type)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n\n[truncated]"

    return DocumentResult(url=url, host=host, content=text, content_type=content_type)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    import requests

    result = fetch_document(url=event["url"], http_session=requests.Session())
    return {
        "url": result.url,
        "host": result.host,
        "content": result.content,
        "content_type": result.content_type,
    }
