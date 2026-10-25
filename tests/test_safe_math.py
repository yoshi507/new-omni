import time

import pytest

from omnibot.services.safe_math import CalcError, evaluate


@pytest.mark.parametrize("expr,expected", [
    ("1+2*3", 7), ("(1+2)*3", 9), ("10/4", 2.5), ("10//4", 2), ("10%4", 2),
    ("2**10", 1024), ("-3+5", 2), ("1.5*2", 3),
])
def test_basic(expr, expected):
    assert evaluate(expr) == expected


@pytest.mark.parametrize("expr", [
    "9**9**9**9", "2**1000", "10**10**10", "9" * 150 + "*" + "9" * 150,
])
def test_huge_inputs_rejected_fast(expr):
    start = time.monotonic()
    with pytest.raises(CalcError):
        evaluate(expr)
    assert time.monotonic() - start < 0.5


@pytest.mark.parametrize("expr", [
    "__import__('os')", "().__class__", "abc", "1/0", "", "x" * 300, "[1,2]", "lambda: 1",
])
def test_rejects_non_math(expr):
    with pytest.raises(CalcError):
        evaluate(expr)
