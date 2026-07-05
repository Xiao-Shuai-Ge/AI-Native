"""`calculator` tool: evaluates a math expression using an AST whitelist.

Per AGENTS.md section 10 ("`calculator` 使用 AST 白名单，不直接执行用户表达式"),
this never calls `eval`/`exec`. Only a fixed set of AST node types and
whitelisted function names are allowed; anything else raises `ToolError`.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable

from pydantic import BaseModel, Field

from mcp_server.errors import ToolError, ToolErrorCode

MAX_EXPRESSION_LENGTH = 200

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_ALLOWED_FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
}

_ALLOWED_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}


class CalculatorInput(BaseModel):
    expression: str = Field(min_length=1, max_length=MAX_EXPRESSION_LENGTH)


class CalculatorOutput(BaseModel):
    result: float


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise ToolError(ToolErrorCode.INVALID_INPUT, "only numeric literals are allowed")
        return float(node.value)
    if isinstance(node, ast.BinOp):
        binary_op = _BINARY_OPERATORS.get(type(node.op))
        if binary_op is None:
            raise ToolError(ToolErrorCode.INVALID_INPUT, "operator is not allowed")
        return binary_op(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        unary_op = _UNARY_OPERATORS.get(type(node.op))
        if unary_op is None:
            raise ToolError(ToolErrorCode.INVALID_INPUT, "unary operator is not allowed")
        return unary_op(_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
            raise ToolError(ToolErrorCode.INVALID_INPUT, "function is not allowed")
        if node.keywords:
            raise ToolError(ToolErrorCode.INVALID_INPUT, "keyword arguments are not allowed")
        args = [_eval_node(arg) for arg in node.args]
        try:
            return float(_ALLOWED_FUNCTIONS[node.func.id](*args))
        except (ValueError, ZeroDivisionError, OverflowError, TypeError) as exc:
            raise ToolError(ToolErrorCode.INVALID_INPUT, "function call failed") from exc
    if isinstance(node, ast.Name):
        if node.id not in _ALLOWED_CONSTANTS:
            raise ToolError(ToolErrorCode.INVALID_INPUT, "identifier is not allowed")
        return _ALLOWED_CONSTANTS[node.id]
    raise ToolError(ToolErrorCode.INVALID_INPUT, "expression contains a disallowed construct")


def evaluate_expression(expression: str) -> float:
    """Evaluates a whitelisted arithmetic expression. Never calls `eval`/`exec`."""
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ToolError(ToolErrorCode.INVALID_INPUT, "expression exceeds maximum length")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError(ToolErrorCode.INVALID_INPUT, "expression is not valid syntax") from exc
    try:
        result = _eval_node(tree)
    except ZeroDivisionError as exc:
        raise ToolError(ToolErrorCode.INVALID_INPUT, "division by zero") from exc
    if not math.isfinite(result):
        raise ToolError(ToolErrorCode.INVALID_INPUT, "result is not a finite number")
    return result


def run_calculator(payload: CalculatorInput) -> CalculatorOutput:
    return CalculatorOutput(result=evaluate_expression(payload.expression))
