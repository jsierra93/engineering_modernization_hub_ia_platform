"""PLAN.md task 2.4 -- the suite-integrity invariant (CLAUDE.md invariant
#2): "the test suite can only grow".

Deterministic zone: this module parses real JUnit XML with the stdlib
`xml.etree.ElementTree` (no heavy dependency, no LLM in the loop -- see
CLAUDE.md invariant #1) and measures the *effect* on the suite, not a
line-level diff. That is what catches deletion, skip marks, pytest config
filters in `pyproject.toml`, and command tampering alike.

pytest's own JUnit writer reports an expected-failure (`xfail`) test as a
`<testcase>` with a `<skipped .../>` child (type `"pytest.xfail"` for a
strict xfail, or a `message` mentioning "xfail" for the common case).
Rather than special-case that string, this module counts *every*
testcase with a `<skipped>` child under one bucket -- "skipped_or_xfailed"
-- which is exactly the union CLAUDE.md's invariant asks for and is
robust to which of the two pytest happens to emit.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET


class JUnitParseError(Exception):
    """Raised when the given string is not parseable JUnit XML."""


@dataclass(frozen=True)
class JUnitSummary:
    """Counts derived from one JUnit XML report.

    `executed` is the total number of `<testcase>` elements present in
    the report -- this is what shrinks if tests are deleted or filtered
    out of collection entirely (a suite that never ran a test can't
    report it as skipped either).
    """

    executed: int
    passed: int
    failed: int
    skipped_or_xfailed: int


def parse_junit(xml_text: str) -> JUnitSummary:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise JUnitParseError(f"invalid JUnit XML: {exc}") from exc

    testcases = root.findall(".//testcase")

    executed = len(testcases)
    failed = 0
    skipped_or_xfailed = 0
    passed = 0

    for testcase in testcases:
        if testcase.find("failure") is not None or testcase.find("error") is not None:
            failed += 1
        elif testcase.find("skipped") is not None:
            skipped_or_xfailed += 1
        else:
            passed += 1

    return JUnitSummary(
        executed=executed,
        passed=passed,
        failed=failed,
        skipped_or_xfailed=skipped_or_xfailed,
    )


class SuiteIntegrityViolation(str):
    """A specific, named violation reason (a plain str subclass so callers
    can compare against these constants or just check "is not None")."""


SUITE_SHRANK = SuiteIntegrityViolation("SUITE_SHRANK")
TESTS_SILENCED = SuiteIntegrityViolation("TESTS_SILENCED")
REGRESSION = SuiteIntegrityViolation("REGRESSION")


def check_suite_integrity(
    baseline: JUnitSummary, final: JUnitSummary
) -> SuiteIntegrityViolation | None:
    """Compare final JUnit results against the baseline.

    Returns `None` if the suite is intact (adding new tests is always
    fine), or one of `SUITE_SHRANK` / `TESTS_SILENCED` / `REGRESSION`
    otherwise. Checked in this order because a run that both shrank the
    suite AND silenced tests should still get one deterministic answer.
    """

    if final.executed < baseline.executed:
        return SUITE_SHRANK
    if final.skipped_or_xfailed > baseline.skipped_or_xfailed:
        return TESTS_SILENCED
    if final.passed < baseline.passed:
        return REGRESSION
    return None
