"""Safe arithmetic evaluator for /util calc (no eval, bounded work)."""
from __future__ import annotations

import ast
import operator

MAX_LEN = 200
MAX_POW_EXPONENT = 100
MAX_ABS_RESULT = 10**100

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class CalcError(ValueError):
    pass


def _check(v: int | float) -> int | float:
    if abs(v) > MAX_ABS_RESULT:
        raise CalcError("Result is too large.")
    return v


def _eval(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return _check(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _check(_UNARY[type(node.op)](_eval(node.operand)))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_POW_EXPONENT:
            raise CalcError(f"Exponent must be at most {MAX_POW_EXPONENT}.")
        # Large left * large right is fine to compute once both are already bounded.
        try:
            return _check(_BIN[type(node.op)](left, right))
        except ZeroDivisionError as e:
            raise CalcError("Division by zero.") from e
        except OverflowError as e:
            raise CalcError("Result is too large.") from e
    raise CalcError("Only numbers and + - * / // % ** ( ) are allowed.")


def evaluate(expression: str) -> int | float:
    expr = (expression or "").strip()
    if not expr:
        raise CalcError("Enter an expression.")
    if len(expr) > MAX_LEN:
        raise CalcError(f"Expression is too long (max {MAX_LEN} characters).")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise CalcError("Could not parse that expression.") from e
    result = _eval(tree)
    if isinstance(result, float) and result.is_integer() and abs(result) < 1e15:
        return int(result)
    return result
