"""A fail-closed evaluator for the small, documented FormulaWitness formula subset."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


class FormulaError(ValueError):
    pass


TOKEN_RE = re.compile(
    r"\s*(?:(?P<number>(?:\d+(?:\.\d*)?|\.\d+))|"
    r'(?P<string>"(?:[^"]|"")*")|'
    r"(?P<sheetcell>(?:'[A-Za-z0-9_ .]+'|[A-Za-z_][A-Za-z0-9_. ]*)!\$?[A-Za-z]{1,3}\$?\d+)|"
    r"(?P<cell>\$?[A-Za-z]{1,3}\$?\d+)|"
    r"(?P<ident>[A-Za-z_][A-Za-z0-9_.]*)|"
    r"(?P<op><=|>=|<>|[=<>+\-*/^(),:]))"
)
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CELL_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d+)$")
QUALIFIED_CELL_RE = re.compile(
    r"^(?:(?P<sheet>[A-Za-z_][A-Za-z0-9_. ]*)!)?(?P<column>[A-Z]{1,3})(?P<row>\d+)$"
)


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


def _normalize_reference(value: str) -> str:
    return value.replace("$", "").replace("'", "").upper()


def _column_index(column: str) -> int:
    result = 0
    for character in column:
        result = result * 26 + ord(character) - 64
    return result


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _expand_range(start: str, end: str) -> list[str]:
    start_match = QUALIFIED_CELL_RE.fullmatch(start)
    end_match = QUALIFIED_CELL_RE.fullmatch(end)
    if not start_match or not end_match:
        raise FormulaError(f"Unsupported range {start}:{end}")
    start_sheet = start_match.group("sheet")
    end_sheet = end_match.group("sheet") or start_sheet
    if start_sheet != end_sheet:
        raise FormulaError("Three-dimensional ranges are unsupported")
    first_column = _column_index(start_match.group("column"))
    last_column = _column_index(end_match.group("column"))
    first_row = int(start_match.group("row"))
    last_row = int(end_match.group("row"))
    if first_column > last_column or first_row > last_row:
        raise FormulaError("Descending ranges are unsupported")
    prefix = f"{start_sheet}!" if start_sheet else ""
    return [
        f"{prefix}{_column_name(column)}{row}"
        for row in range(first_row, last_row + 1)
        for column in range(first_column, last_column + 1)
    ]


def tokenize(formula: str) -> list[Token]:
    text = formula.removeprefix("=")
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        match = TOKEN_RE.match(text, pos)
        if not match:
            raise FormulaError(f"Unsupported token at position {pos}: {text[pos : pos + 16]!r}")
        kind = match.lastgroup
        assert kind is not None
        tokens.append(Token(kind, match.group(kind)))
        pos = match.end()
    tokens.append(Token("eof", ""))
    return tokens


class Parser:
    def __init__(self, formula: str):
        self.tokens = tokenize(formula)
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def take(self, value: str | None = None) -> Token:
        token = self.current
        if value is not None and token.value != value:
            raise FormulaError(f"Expected {value!r}; found {token.value!r}")
        self.index += 1
        return token

    def parse(self) -> Any:
        result = self.comparison()
        if self.current.kind != "eof":
            raise FormulaError(f"Unexpected token {self.current.value!r}")
        return result

    def comparison(self) -> Any:
        left = self.additive()
        if self.current.value in {"=", "<>", "<", ">", "<=", ">="}:
            op = self.take().value
            return ("binary", op, left, self.additive())
        return left

    def additive(self) -> Any:
        left = self.multiplicative()
        while self.current.value in {"+", "-"}:
            op = self.take().value
            left = ("binary", op, left, self.multiplicative())
        return left

    def multiplicative(self) -> Any:
        left = self.unary()
        while self.current.value in {"*", "/"}:
            op = self.take().value
            left = ("binary", op, left, self.unary())
        return left

    def unary(self) -> Any:
        if self.current.value in {"+", "-"}:
            return ("unary", self.take().value, self.unary())
        return self.primary()

    def primary(self) -> Any:
        token = self.current
        if token.kind == "number":
            self.take()
            return ("literal", Decimal(token.value))
        if token.kind == "string":
            self.take()
            return ("literal", token.value[1:-1].replace('""', '"'))
        if token.kind in {"cell", "sheetcell"}:
            self.take()
            start = _normalize_reference(token.value)
            if self.current.value == ":":
                self.take(":")
                end_token = self.take()
                if end_token.kind not in {"cell", "sheetcell"}:
                    raise FormulaError("Range endpoint must be a cell")
                end = _normalize_reference(end_token.value)
                if "!" not in end and "!" in start:
                    end = f"{start.split('!', 1)[0]}!{end}"
                return ("range", start, end)
            return ("cell", start)
        if token.kind == "ident":
            name = self.take().value.upper()
            self.take("(")
            args: list[Any] = []
            if self.current.value != ")":
                while True:
                    args.append(self.comparison())
                    if self.current.value != ",":
                        break
                    self.take(",")
            self.take(")")
            return ("call", name, tuple(args))
        if token.value == "(":
            self.take("(")
            value = self.comparison()
            self.take(")")
            return value
        raise FormulaError(f"Unexpected token {token.value!r}")


def _number(value: Any) -> Decimal:
    if isinstance(value, bool):
        return Decimal(1 if value else 0)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    if value in (None, ""):
        return Decimal(0)
    raise FormulaError(f"Expected number, found {value!r}")


def _excel_round(value: Decimal, digits: int) -> Decimal:
    quantum = Decimal(1).scaleb(-digits)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def evaluate_ast(ast: Any, resolve_cell: Callable[[str], Any]) -> Any:
    kind = ast[0]
    if kind == "literal":
        return ast[1]
    if kind == "cell":
        return resolve_cell(ast[1])
    if kind == "range":
        return [resolve_cell(cell) for cell in _expand_range(ast[1], ast[2])]
    if kind == "unary":
        value = _number(evaluate_ast(ast[2], resolve_cell))
        return value if ast[1] == "+" else -value
    if kind == "binary":
        op = ast[1]
        left = evaluate_ast(ast[2], resolve_cell)
        right = evaluate_ast(ast[3], resolve_cell)
        if op in {"=", "<>", "<", ">", "<=", ">="}:
            if isinstance(left, str) or isinstance(right, str):
                text_left, text_right = str(left), str(right)
                return {
                    "=": text_left == text_right,
                    "<>": text_left != text_right,
                    "<": text_left < text_right,
                    ">": text_left > text_right,
                    "<=": text_left <= text_right,
                    ">=": text_left >= text_right,
                }[op]
            number_left, number_right = _number(left), _number(right)
            return {
                "=": number_left == number_right,
                "<>": number_left != number_right,
                "<": number_left < number_right,
                ">": number_left > number_right,
                "<=": number_left <= number_right,
                ">=": number_left >= number_right,
            }[op]
        numeric_left, numeric_right = _number(left), _number(right)
        if op == "+":
            return numeric_left + numeric_right
        if op == "-":
            return numeric_left - numeric_right
        if op == "*":
            return numeric_left * numeric_right
        if op == "/":
            if numeric_right == 0:
                raise FormulaError("Division by zero")
            return numeric_left / numeric_right
        raise FormulaError(f"Unsupported operator {op}")
    if kind == "call":
        name, args = ast[1], ast[2]
        if name == "IF":
            if len(args) != 3:
                raise FormulaError("IF requires three arguments")
            return evaluate_ast(
                args[1] if bool(evaluate_ast(args[0], resolve_cell)) else args[2], resolve_cell
            )
        values = [evaluate_ast(arg, resolve_cell) for arg in args]
        if name == "AND":
            return all(bool(value) for value in values)
        if name == "OR":
            return any(bool(value) for value in values)
        if name == "MAX":
            return max(_number(value) for value in values)
        if name == "MIN":
            return min(_number(value) for value in values)
        if name == "ROUND":
            if len(values) != 2:
                raise FormulaError("ROUND requires two arguments")
            return _excel_round(_number(values[0]), int(_number(values[1])))
        if name == "LOOKUP":
            if (
                len(values) != 3
                or not isinstance(values[1], list)
                or not isinstance(values[2], list)
            ):
                raise FormulaError("LOOKUP requires a value and two ranges")
            lookup_values = [_number(value) for value in values[1]]
            if lookup_values != sorted(lookup_values) or len(lookup_values) != len(values[2]):
                raise FormulaError("LOOKUP ranges must be aligned and ascending")
            needle = _number(values[0])
            eligible = [index for index, value in enumerate(lookup_values) if value <= needle]
            if not eligible:
                raise FormulaError("LOOKUP value is below the first lower bound")
            return values[2][eligible[-1]]
        raise FormulaError(f"Unsupported function {name}")
    raise FormulaError(f"Unsupported AST node {kind}")


def referenced_cells(formula: str) -> list[str]:
    references: set[str] = set()

    def visit(ast: Any) -> None:
        if ast[0] == "cell":
            references.add(ast[1])
        elif ast[0] == "range":
            references.update(_expand_range(ast[1], ast[2]))
        elif ast[0] == "binary":
            visit(ast[2])
            visit(ast[3])
        elif ast[0] == "unary":
            visit(ast[2])
        elif ast[0] == "call":
            for argument in ast[2]:
                visit(argument)

    visit(Parser(formula).parse())
    return sorted(references)


def excel_serial(value: str | date | datetime | float | Decimal) -> Decimal:
    if isinstance(value, str):
        parsed = date.fromisoformat(value)
    elif isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        return Decimal(str(value))
    return Decimal((parsed - date(1899, 12, 30)).days)


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def evaluate_cells(
    raw_values: dict[str, Any],
    formulas: dict[str, str],
    overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    values = {key.upper(): value for key, value in raw_values.items()}
    for key, value in (overrides or {}).items():
        cell = key.upper()
        values[cell] = (
            excel_serial(value)
            if isinstance(value, str) and ISO_DATE_RE.fullmatch(value)
            else value
        )
    memo: dict[str, Any] = {}
    active: set[str] = set()
    dependencies = {cell.upper(): referenced_cells(formula) for cell, formula in formulas.items()}

    def resolve(cell: str) -> Any:
        cell = cell.upper()
        if cell in memo:
            return memo[cell]
        if cell in active:
            raise FormulaError(f"Circular reference at {cell}")
        if cell in formulas:
            active.add(cell)
            memo[cell] = evaluate_ast(Parser(formulas[cell]).parse(), resolve)
            active.remove(cell)
            return memo[cell]
        if cell not in values:
            raise FormulaError(f"Missing cell {cell}")
        return values[cell]

    for cell in formulas:
        resolve(cell)
    return {cell: json_value(value) for cell, value in memo.items()}, dependencies
