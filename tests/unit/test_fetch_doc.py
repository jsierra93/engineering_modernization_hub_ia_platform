"""Task 3.6: `fetch_doc` restricts documentation fetches to an allowlist
of domains, with a real subdomain-vs-suffix boundary check, HTTPS-only,
and a response size cap. Mirrors `tests/unit/test_fetch_repo.py`'s style
(mocked HTTP via `responses`, no network).
"""

from __future__ import annotations

import requests
import responses

from fetch_doc.allowlist import ALLOWED_DOMAINS, is_allowed_host
from fetch_doc.handler import (
    MAX_RESPONSE_BYTES,
    DisallowedHostError,
    DisallowedSchemeError,
    ResponseTooLargeError,
    fetch_document,
)


def test_allowlisted_url_fetches_successfully():
    url = "https://docs.pydantic.dev/latest/migration/"

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            url,
            body="<html>migration guide</html>",
            status=200,
            content_type="text/html",
        )
        result = fetch_document(url, http_session=requests.Session())

    assert result.url == url
    assert result.host == "docs.pydantic.dev"
    assert "migration guide" in result.content
    assert result.content_type == "text/html"


def test_non_allowlisted_domain_is_rejected_without_any_request():
    url = "https://evil.example.com/docs"

    with responses.RequestsMock() as rsps:
        try:
            fetch_document(url, http_session=requests.Session())
            raised = False
        except DisallowedHostError:
            raised = True

    assert raised
    # No mocked route was registered and none was called -- the allowlist
    # check must happen before any network attempt.
    assert len(rsps.calls) == 0


def test_subdomain_spoofing_trap_is_rejected():
    """`docs.pydantic.dev.evil.com` contains the allowlisted domain as a
    literal substring but is NOT a subdomain of it -- a naive `in` check
    would wrongly allow this."""

    url = "https://docs.pydantic.dev.evil.com/migration/"

    with responses.RequestsMock() as rsps:
        try:
            fetch_document(url, http_session=requests.Session())
            raised = False
        except DisallowedHostError:
            raised = True

    assert raised
    assert len(rsps.calls) == 0


def test_genuine_subdomain_of_an_allowed_domain_is_allowed():
    assert is_allowed_host("sub.docs.pydantic.dev")
    assert not is_allowed_host("docs.pydantic.dev.evil.com")
    assert not is_allowed_host("notdocs.pydantic.dev")


def test_non_https_url_is_rejected():
    url = "http://docs.pydantic.dev/latest/migration/"

    with responses.RequestsMock() as rsps:
        try:
            fetch_document(url, http_session=requests.Session())
            raised = False
        except DisallowedSchemeError:
            raised = True

    assert raised
    assert len(rsps.calls) == 0


def test_oversized_response_is_rejected():
    url = "https://docs.python.org/3/whatsnew/3.13.html"
    oversized_body = "x" * (MAX_RESPONSE_BYTES + 1)

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, url, body=oversized_body, status=200)
        try:
            fetch_document(url, http_session=requests.Session())
            raised = False
        except ResponseTooLargeError:
            raised = True

    assert raised


def test_allowlist_contains_only_the_expected_small_set():
    assert ALLOWED_DOMAINS == {
        "docs.pydantic.dev",
        "docs.python.org",
        "pypi.org",
        "osv.dev",
    }
