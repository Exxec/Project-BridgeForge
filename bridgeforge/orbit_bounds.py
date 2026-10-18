"""Interval proof for an orbit-period expression (ROADMAP item 73 B1, revised by item 75 R4).

`Math.max(1f, E)` repairs a zero or negative period. It does NOT repair NaN (`Math.max(1f, NaN)` is NaN) or infinity
(`Math.max(1f, +inf)` is +inf), which also fail the save with "JSON does not allow non-finite numbers". So a clamp is
only a repair when `E` is proven finite and has an evidenced finite lower bound. This module proves both or refuses.

Supported: numeric literals, `Math.random()` (in [0, 1)), `+ - * /`, unary minus, parentheses, `(int|long|float|double)`
casts, and local variables with exactly one assignment (a one-line declaration) whose initializer is itself supported.
Everything else is unproven and raises `Unproven` with the reason: any other call (side effects, unknown range), `++`,
`--`, compound assignment, a field, a float/double parameter (may be NaN or infinite), an unbounded integer parameter,
a divisor whose interval contains zero. Integer division widens its interval by one on each side.

`prove(expression, method_text)` returns `(low, high)`; the caller requires `low` to be finite and below 1.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+\.\d*(?:[eE][-+]?\d+)?[fFdD]?|\.\d+[fFdD]?|\d+[fFdDlL]?)|(?P<call>Math\s*\.\s*random\s*\(\s*\))"
    r"|(?P<cast>\(\s*(?:int|long|float|double)\s*\))|(?P<id>[A-Za-z_$][\w$]*)|(?P<op>[-+*/()]))"
)
_FORBIDDEN_CHARS = re.compile(r"\+\+|--|[=!<>?:&|%\[\].]")
_DECLARATION = r"\b(?:final\s+)?(?:int|long|short|byte|float|double)\s+{name}\s*=(?!=)\s*([^;]+);"
_MAX_DEPTH = 6


class Unproven(ValueError):
    """The expression is not provably finite and bounded; the reason is the message."""


@dataclass(frozen=True)
class Interval:
    low: float
    high: float
    integral: bool = False

    def contains_zero(self) -> bool:
        return self.low <= 0 <= self.high


def _mul(a: float, b: float) -> float:
    return 0.0 if (a == 0 or b == 0) else a * b


def _times(x: Interval, y: Interval) -> Interval:
    products = [_mul(a, b) for a in (x.low, x.high) for b in (y.low, y.high)]
    return Interval(min(products), max(products), x.integral and y.integral)


def _divide(x: Interval, y: Interval) -> Interval:
    if y.contains_zero():
        raise Unproven("a divisor may be zero, which gives infinity or NaN")
    inverse = Interval(1 / y.high if y.high not in (math.inf, -math.inf) else 0.0, 1 / y.low if y.low not in (math.inf, -math.inf) else 0.0)
    low, high = sorted((inverse.low, inverse.high))
    result = _times(x, Interval(low, high, False))
    if x.integral and y.integral:
        return Interval(result.low - 1, result.high + 1, True)
    return Interval(result.low, result.high, False)


class _Parser:
    def __init__(self, text: str, method_text: str, depth: int, seen: frozenset[str]):
        self.method, self.depth, self.seen = method_text, depth, seen
        if _FORBIDDEN_CHARS.search(re.sub(r"\d+\.\d*|\.\d+|Math\s*\.\s*random\s*\(\s*\)", "0", text)):
            raise Unproven("the expression has an operator, call or member access outside the supported arithmetic")
        self.tokens: list[tuple[str, str]] = []
        position = 0
        while position < len(text):
            match = _TOKEN.match(text, position)
            if match is None or match.end() == position:
                if text[position:].strip():
                    raise Unproven(f"unsupported syntax near '{text[position:position + 12].strip()}'")
                break
            kind = match.lastgroup or ""
            self.tokens.append((kind, match.group(kind).strip()))
            position = match.end()
        self.index = 0

    def _peek(self) -> tuple[str, str] | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def parse(self) -> Interval:
        value = self._sum()
        if self._peek() is not None:
            raise Unproven("trailing tokens after the expression")
        return value

    def _sum(self) -> Interval:
        value = self._product()
        while (token := self._peek()) and token[0] == "op" and token[1] in "+-":
            self.index += 1
            right = self._product()
            if token[1] == "+":
                value = Interval(value.low + right.low, value.high + right.high, value.integral and right.integral)
            else:
                value = Interval(value.low - right.high, value.high - right.low, value.integral and right.integral)
        return value

    def _product(self) -> Interval:
        value = self._unary()
        while (token := self._peek()) and token[0] == "op" and token[1] in "*/":
            self.index += 1
            right = self._unary()
            value = _times(value, right) if token[1] == "*" else _divide(value, right)
        return value

    def _unary(self) -> Interval:
        token = self._peek()
        if token and token[0] == "op" and token[1] in "+-":
            self.index += 1
            value = self._unary()
            return value if token[1] == "+" else Interval(-value.high, -value.low, value.integral)
        if token and token[0] == "cast":
            self.index += 1
            value = self._unary()
            if "int" in token[1] or "long" in token[1]:
                return Interval(math.floor(value.low) if math.isfinite(value.low) else value.low,
                                math.ceil(value.high) if math.isfinite(value.high) else value.high, True)
            return Interval(value.low, value.high, False)
        return self._atom()

    def _atom(self) -> Interval:
        token = self._peek()
        if token is None:
            raise Unproven("the expression ends unexpectedly")
        self.index += 1
        kind, text = token
        if kind == "num":
            number = float(text.rstrip("fFdDlL"))
            return Interval(number, number, text[-1] in "lL" or re.fullmatch(r"\d+", text) is not None)
        if kind == "call":
            return Interval(0.0, 1.0, False)
        if kind == "id":
            return self._variable(text)
        if kind == "op" and text == "(":
            value = self._sum()
            closing = self._peek()
            if closing is None or closing[1] != ")":
                raise Unproven("unbalanced parentheses")
            self.index += 1
            return value
        raise Unproven(f"unsupported token '{text}'")

    def _variable(self, name: str) -> Interval:
        if self.depth >= _MAX_DEPTH or name in self.seen:
            raise Unproven(f"'{name}' is defined in terms of itself or too deeply to prove")
        assignments = len(re.findall(rf"(?<![\w.$]){re.escape(name)}\s*(?:[-+*/%&|^]|<<|>>>?)?=(?!=)", self.method))
        declaration = re.findall(_DECLARATION.format(name=re.escape(name)), self.method)
        if len(declaration) == 1 and assignments == 1 and not re.search(rf"(?:\+\+|--)\s*{re.escape(name)}\b|\b{re.escape(name)}\s*(?:\+\+|--)", self.method):
            return _Parser(declaration[0], self.method, self.depth + 1, self.seen | {name}).parse()
        raise Unproven(f"'{name}' is a parameter, field or reassigned variable, so its range is unknown (NaN or infinity possible)")


def prove(expression: str, method_text: str, depth: int = 0, seen: frozenset[str] = frozenset()) -> tuple[float, float]:
    """(low, high) of `expression`, or raise Unproven. Both bounds finite means a clamp at 1 repairs every possible value."""
    interval = _Parser(expression, method_text, depth, seen).parse()
    return interval.low, interval.high
