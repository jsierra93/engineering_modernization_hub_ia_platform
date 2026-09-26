"""Domain allowlist for `fetch_doc` (PLAN.md task 3.6).

This service gets **zero AWS permissions, ever** (CLAUDE.md's permissions
table, PLAN.md 3.6-tf). The only control it has is the allowlist: the
agent may ask it to fetch "official documentation" for whatever URL it
wants, and this module is what stops that from becoming an open SSRF-ish
fetch proxy. Everything returned still crosses into the prompt as
untrusted data (CLAUDE.md invariant #9) -- the allowlist bounds *where*
it may come from, not whether it's trustworthy once fetched.

Kept intentionally small and matched to what actually exists today,
rather than padded speculatively:

- `docs.pydantic.dev` -- the one real strategy in this prototype,
  `python-pydantic-v2`, declares this exact host in its manifest's
  `sources` (`strategies/python_pydantic_v2/src/python_pydantic_v2/
  manifest.py`). Without it, the only shipped strategy couldn't use this
  tool at all.
- `docs.python.org` -- the artifact's "Fuentes" section names "release
  notes" and "migration guides" as legitimate source categories; the
  official Python docs (What's New / migration guides) are the canonical
  home for both, for any future strategy that bumps a Python version
  rather than (or in addition to) a library version.
- `pypi.org` -- the same "Fuentes" section names "package registries";
  PyPI project pages are the canonical place to confirm a package's
  current version, supported Python range, and changelog links before
  proposing a migration.
- `osv.dev` -- the same section names "security advisories"; the
  Open Source Vulnerability database is the standard source for those,
  and PLAN.md's Plus section already names a future "remediar
  dependencia vulnerable" strategy that would need exactly this.

Adding a fifth entry for a strategy that doesn't exist yet is exactly
the speculative padding this module is trying to avoid -- extend this
list when the strategy that needs it actually lands.
"""

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
    """True if `host` is exactly an allowlisted domain, or a subdomain of
    one.

    Boundary rule, deliberately not a substring check: `host` must equal
    an allowed domain, or end with `"." + allowed_domain`. A naive
    `allowed_domain in host` would let `docs.pydantic.dev.evil.com`
    through (it contains the substring "docs.pydantic.dev") -- this
    checks the *suffix after a dot boundary* instead, so that URL is
    correctly rejected while a genuine subdomain like
    `sub.docs.pydantic.dev` is correctly allowed.
    """

    host = host.lower().rstrip(".")
    for domain in ALLOWED_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False
