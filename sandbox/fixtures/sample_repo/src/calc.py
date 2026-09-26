"""Tiny module the fixture's tests exercise."""


def add(a: int, b: int) -> int:
    return a + b


def divide(a: int, b: int) -> float:
    return a / b


def is_even(n: int) -> bool:
    return n % 2 == 0
