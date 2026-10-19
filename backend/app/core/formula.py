"""Work out a rule's formula, such as "4.5 + 0.04 * L", from the rule file.

Only arithmetic is allowed: numbers, named values, + - * / **, brackets, and sqrt, min, max.
The formula is never run as Python code, so a rule file cannot make the server do anything else.
"""
import ast
import math
import operator

OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow,
             ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCTIONS = {"sqrt": math.sqrt, "min": min, "max": max}


def evaluate(formula: str, values: dict) -> float:
    """values: the named quantities the formula may use, e.g. {"L": 142.0, "s": 700.0}."""

    def work_out(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise ValueError(f"'{node.id}' is not a quantity this formula can use ({', '.join(sorted(values))})")
            return values[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](work_out(node.left), work_out(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](work_out(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
            return FUNCTIONS[node.func.id](*(work_out(argument) for argument in node.args))
        raise ValueError("only numbers, named quantities, + - * / **, brackets, sqrt, min and max are allowed")

    try:
        return float(work_out(ast.parse(formula, mode="eval").body))
    except (SyntaxError, ZeroDivisionError, OverflowError, TypeError) as e:
        raise ValueError(f"the formula '{formula}' cannot be worked out: {e}") from e
