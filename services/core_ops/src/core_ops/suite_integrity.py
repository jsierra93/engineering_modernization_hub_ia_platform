"""Parses JUnit and checks the suite can only grow (invariant 2), measuring effect rather than diff."""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET


class JUnitParseError(Exception):
    pass


@dataclass(frozen=True)
class JUnitSummary:
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
    pass


SUITE_SHRANK = SuiteIntegrityViolation("SUITE_SHRANK")
TESTS_SILENCED = SuiteIntegrityViolation("TESTS_SILENCED")
REGRESSION = SuiteIntegrityViolation("REGRESSION")


def check_suite_integrity(
    baseline: JUnitSummary, final: JUnitSummary
) -> SuiteIntegrityViolation | None:
    if final.executed < baseline.executed:
        return SUITE_SHRANK
    if final.skipped_or_xfailed > baseline.skipped_or_xfailed:
        return TESTS_SILENCED
    if final.passed < baseline.passed:
        return REGRESSION
    return None
