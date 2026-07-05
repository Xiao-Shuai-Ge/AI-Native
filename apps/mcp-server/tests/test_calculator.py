"""Unit tests for the `calculator` tool."""

from __future__ import annotations

import pytest

from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.tools.calculator import (
    MAX_EXPRESSION_LENGTH,
    CalculatorInput,
    evaluate_expression,
    run_calculator,
)


def test_evaluates_basic_arithmetic() -> None:
    assert evaluate_expression("1 + 2 * 3") == 7
    assert evaluate_expression("(2 + 3) / 5") == 1.0
    assert evaluate_expression("2 ** 10") == 1024


def test_evaluates_whitelisted_functions_and_constants() -> None:
    assert evaluate_expression("sqrt(16)") == 4.0
    assert round(evaluate_expression("sin(0) + cos(0)"), 5) == 1.0
    assert round(evaluate_expression("pi"), 5) == round(3.14159, 5)


def test_rejects_disallowed_names() -> None:
    with pytest.raises(ToolError) as excinfo:
        evaluate_expression("__import__('os').system('ls')")
    assert excinfo.value.code == ToolErrorCode.INVALID_INPUT


def test_rejects_arbitrary_calls() -> None:
    with pytest.raises(ToolError) as excinfo:
        evaluate_expression("open('/etc/passwd').read()")
    assert excinfo.value.code == ToolErrorCode.INVALID_INPUT


def test_rejects_invalid_syntax() -> None:
    with pytest.raises(ToolError) as excinfo:
        evaluate_expression("1 +")
    assert excinfo.value.code == ToolErrorCode.INVALID_INPUT


def test_rejects_division_by_zero() -> None:
    with pytest.raises(ToolError) as excinfo:
        evaluate_expression("1 / 0")
    assert excinfo.value.code == ToolErrorCode.INVALID_INPUT


def test_rejects_expression_over_max_length() -> None:
    with pytest.raises(ToolError):
        evaluate_expression("1+" * MAX_EXPRESSION_LENGTH)


def test_run_calculator_returns_structured_output() -> None:
    output = run_calculator(CalculatorInput(expression="4 * 4"))
    assert output.result == 16
