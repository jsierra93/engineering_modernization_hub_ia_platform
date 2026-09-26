"""Task 2.4: the suite can only grow -- three violation cases plus the
valid case, parsed from real JUnit XML strings (not mocked objects), per
PLAN.md's "Hecho cuando"."""

from __future__ import annotations

from core_ops.suite_integrity import (
    REGRESSION,
    SUITE_SHRANK,
    TESTS_SILENCED,
    check_suite_integrity,
    parse_junit,
)

BASELINE_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="4" failures="0" errors="0" skipped="1">
  <testcase classname="t" name="test_a" time="0.01" />
  <testcase classname="t" name="test_b" time="0.01" />
  <testcase classname="t" name="test_c" time="0.01" />
  <testcase classname="t" name="test_d" time="0.01">
    <skipped message="not ready yet" type="pytest.skip" />
  </testcase>
</testsuite>
"""


def _junit(testcases_xml: str, *, tests: int) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="{tests}">
{testcases_xml}
</testsuite>
"""


def test_valid_case_new_tests_added_is_ok():
    baseline = parse_junit(BASELINE_XML)

    final_xml = _junit(
        """
  <testcase classname="t" name="test_a" time="0.01" />
  <testcase classname="t" name="test_b" time="0.01" />
  <testcase classname="t" name="test_c" time="0.01" />
  <testcase classname="t" name="test_d" time="0.01">
    <skipped message="not ready yet" type="pytest.skip" />
  </testcase>
  <testcase classname="t" name="test_e_new" time="0.01" />
""",
        tests=5,
    )
    final = parse_junit(final_xml)

    assert check_suite_integrity(baseline, final) is None


def test_suite_shrank_when_executed_count_drops():
    baseline = parse_junit(BASELINE_XML)

    final_xml = _junit(
        """
  <testcase classname="t" name="test_a" time="0.01" />
  <testcase classname="t" name="test_b" time="0.01" />
  <testcase classname="t" name="test_d" time="0.01">
    <skipped message="not ready yet" type="pytest.skip" />
  </testcase>
""",
        tests=3,
    )
    final = parse_junit(final_xml)

    assert check_suite_integrity(baseline, final) == SUITE_SHRANK


def test_tests_silenced_when_skipped_plus_xfailed_grows():
    baseline = parse_junit(BASELINE_XML)

    final_xml = _junit(
        """
  <testcase classname="t" name="test_a" time="0.01" />
  <testcase classname="t" name="test_b" time="0.01">
    <skipped message="expected test failure" type="pytest.xfail" />
  </testcase>
  <testcase classname="t" name="test_c" time="0.01" />
  <testcase classname="t" name="test_d" time="0.01">
    <skipped message="not ready yet" type="pytest.skip" />
  </testcase>
""",
        tests=4,
    )
    final = parse_junit(final_xml)

    assert check_suite_integrity(baseline, final) == TESTS_SILENCED


def test_regression_when_passed_count_drops():
    baseline = parse_junit(BASELINE_XML)

    final_xml = _junit(
        """
  <testcase classname="t" name="test_a" time="0.01" />
  <testcase classname="t" name="test_b" time="0.01">
    <failure message="AssertionError">boom</failure>
  </testcase>
  <testcase classname="t" name="test_c" time="0.01" />
  <testcase classname="t" name="test_d" time="0.01">
    <skipped message="not ready yet" type="pytest.skip" />
  </testcase>
""",
        tests=4,
    )
    final = parse_junit(final_xml)

    assert check_suite_integrity(baseline, final) == REGRESSION


def test_parse_junit_counts_errors_as_failed_not_passed():
    xml = _junit(
        """
  <testcase classname="t" name="test_a" time="0.01">
    <error message="boom">traceback</error>
  </testcase>
""",
        tests=1,
    )
    summary = parse_junit(xml)

    assert summary.executed == 1
    assert summary.failed == 1
    assert summary.passed == 0
    assert summary.skipped_or_xfailed == 0
