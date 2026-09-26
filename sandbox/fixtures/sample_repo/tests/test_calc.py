"""A deliberate mix: two passing tests and one failing test.

The failing test is intentional and worth documenting (see
sandbox/README.md): it demonstrates that `unit_tests` produces a real,
parseable JUnit report even when the suite is not 100% green, and that
the check's own exit code is non-zero in that case — exactly the signal
core_ops (a different task, 2.4/2.5) needs to compute a verdict.
"""

from src.calc import add, divide, is_even


def test_add():
    assert add(2, 3) == 5


def test_is_even():
    assert is_even(4) is True
    assert is_even(3) is False


def test_divide_intentionally_wrong():
    # Intentional failure: real division truncated wrong on purpose to
    # prove the sandbox reports a genuine failure rather than always
    # reporting green.
    assert divide(10, 2) == 6
