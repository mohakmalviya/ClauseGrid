"""A fail-closed evaluator for the small, documented FormulaWitness formula subset."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal


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
MAX_EXCEL_COLUMNS = 16_384
MAX_EXCEL_ROWS = 1_048_576
MAX_RANGE_CELLS = 10_000
SUPPORTED_FUNCTIONS = frozenset({"IF", "AND", "OR", "MAX", "MIN", "ROUND", "LOOKUP", "COUNTIF"})


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
    if (
        first_column > MAX_EXCEL_COLUMNS
        or last_column > MAX_EXCEL_COLUMNS
        or first_row < 1
        or last_row < 1
        or first_row > MAX_EXCEL_ROWS
        or last_row > MAX_EXCEL_ROWS
    ):
        raise FormulaError("Cell reference exceeds the Excel worksheet grid")
    if first_column > last_column or first_row > last_row:
        raise FormulaError("Descending ranges are unsupported")
    cell_count = (last_column - first_column + 1) * (last_row - first_row + 1)
    if cell_count > MAX_RANGE_CELLS:
        raise FormulaError(f"Formula range exceeds the {MAX_RANGE_CELLS}-cell safety limit")
    prefix = f"{start_sheet}!" if start_sheet else ""
    return [
        f"{prefix}{_column_name(column)}{row}"
        for row in range(first_row, last_row + 1)
        for column in range(first_column, last_column + 1)
    ]


def _range_shape(start: str, end: str) -> tuple[int, int]:
    start_match = QUALIFIED_CELL_RE.fullmatch(start)
    end_match = QUALIFIED_CELL_RE.fullmatch(end)
    if start_match is None or end_match is None:
        raise FormulaError("Invalid cell range")
    rows = int(end_match.group("row")) - int(start_match.group("row")) + 1
    columns = (
        _column_index(end_match.group("column")) - _column_index(start_match.group("column")) + 1
    )
    return rows, columns


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
            _validate_reference(start)
            if self.current.value == ":":
                self.take(":")
                end_token = self.take()
                if end_token.kind not in {"cell", "sheetcell"}:
                    raise FormulaError("Range endpoint must be a cell")
                end = _normalize_reference(end_token.value)
                if "!" not in end and "!" in start:
                    end = f"{start.split('!', 1)[0]}!{end}"
                _validate_reference(end)
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


def _validate_reference(reference: str) -> None:
    match = QUALIFIED_CELL_RE.fullmatch(reference)
    if match is None:
        raise FormulaError(f"Unsupported cell reference {reference}")
    if (
        _column_index(match.group("column")) > MAX_EXCEL_COLUMNS
        or int(match.group("row")) < 1
        or int(match.group("row")) > MAX_EXCEL_ROWS
    ):
        raise FormulaError("Cell reference exceeds the Excel worksheet grid")


def validate_formula_subset(formula: str) -> None:
    """Reject formulas the isolated evaluator cannot execute before a model run starts."""

    def require_scalar(kind: str, context: str) -> None:
        if kind != "scalar":
            raise FormulaError(f"{context} requires scalar arguments")

    def visit(ast: Any) -> str:
        kind = ast[0]
        if kind == "range":
            _expand_range(ast[1], ast[2])
            return "range"
        if kind in {"literal", "cell"}:
            return "scalar"
        if kind == "unary":
            require_scalar(visit(ast[2]), "Unary arithmetic")
            return "scalar"
        if kind == "binary":
            require_scalar(visit(ast[2]), "Binary operators")
            require_scalar(visit(ast[3]), "Binary operators")
            return "scalar"
        if kind != "call":
            raise FormulaError(f"Unsupported AST node {kind}")
        name, args = ast[1], ast[2]
        if name not in SUPPORTED_FUNCTIONS:
            raise FormulaError(f"Unsupported function {name}")
        required_arity = {"IF": 3, "ROUND": 2, "LOOKUP": 3, "COUNTIF": 2}.get(name)
        if required_arity is not None and len(args) != required_arity:
            raise FormulaError(f"{name} requires {required_arity} arguments")
        if name in {"AND", "OR", "MAX", "MIN"} and not args:
            raise FormulaError(f"{name} requires at least one argument")
        argument_kinds = [visit(argument) for argument in args]
        if name == "LOOKUP":
            require_scalar(argument_kinds[0], "LOOKUP's search value")
            if argument_kinds[1:] != ["range", "range"]:
                raise FormulaError("LOOKUP requires a value and two ranges")
            lookup_shape = _range_shape(args[1][1], args[1][2])
            result_shape = _range_shape(args[2][1], args[2][2])
            if lookup_shape != result_shape or min(lookup_shape) != 1:
                raise FormulaError("LOOKUP requires matching one-dimensional ranges")
        elif name == "COUNTIF":
            if argument_kinds != ["range", "scalar"]:
                raise FormulaError("COUNTIF requires a range and one equality criterion")
            criterion = args[1]
            if criterion[0] != "literal":
                raise FormulaError("COUNTIF requires a literal equality criterion")
            if isinstance(criterion[1], str) and (
                any(marker in criterion[1] for marker in ("*", "?"))
                or criterion[1].startswith(("<", ">", "="))
            ):
                raise FormulaError("COUNTIF accepts only literal equality criteria")
        else:
            for argument_kind in argument_kinds:
                require_scalar(argument_kind, name)
        return "scalar"

    try:
        require_scalar(visit(Parser(formula).parse()), "A worksheet formula")
    except RecursionError as exc:
        raise FormulaError("Formula nesting exceeds the parser safety limit") from exc


def validate_formula_dependency_graph(
    formulas: Mapping[str, str],
    sheet_names: Iterable[str],
    *,
    max_dependencies: int = 100_000,
    max_dependency_depth: int = 200,
) -> None:
    """Validate sheet identity, one-sheet execution constraints, and acyclic formula edges."""

    canonical_sheets = {name.upper() for name in sheet_names}
    canonical_formulas = {reference.upper(): formula for reference, formula in formulas.items()}
    graph: dict[str, set[str]] = {reference: set() for reference in canonical_formulas}
    dependency_count = 0
    for source_reference, formula in canonical_formulas.items():
        source_sheet = source_reference.rsplit("!", 1)[0]
        if source_sheet not in canonical_sheets:
            raise FormulaError(f"Formula source sheet does not exist: {source_reference}")
        remaining_budget = max_dependencies - dependency_count
        try:
            dependencies = referenced_cells(formula, max_references=remaining_budget)
        except FormulaError as exc:
            if "reference expansion exceeds" in str(exc):
                raise FormulaError(
                    f"Workbook formulas exceed the {max_dependencies}-dependency safety limit"
                ) from exc
            raise
        dependency_count += len(dependencies)
        if dependency_count > max_dependencies:
            raise FormulaError(
                f"Workbook formulas exceed the {max_dependencies}-dependency safety limit"
            )
        for dependency in dependencies:
            if "!" in dependency:
                dependency_sheet, cell = dependency.rsplit("!", 1)
            else:
                dependency_sheet, cell = source_sheet, dependency
            if dependency_sheet not in canonical_sheets:
                raise FormulaError(
                    f"Formula references a worksheet that does not exist: {dependency_sheet}"
                )
            canonical_dependency = f"{dependency_sheet}!{cell}"
            if canonical_dependency not in canonical_formulas:
                continue
            if dependency_sheet != source_sheet:
                raise FormulaError(
                    "Cross-sheet formula-to-formula dependencies are outside the supported "
                    f"experiment profile: {source_reference} -> {canonical_dependency}"
                )
            graph[source_reference].add(canonical_dependency)

    remaining_dependencies = {
        reference: len(dependencies) for reference, dependencies in graph.items()
    }
    dependents: dict[str, set[str]] = {reference: set() for reference in graph}
    for source, graph_dependencies in graph.items():
        for dependency in graph_dependencies:
            dependents[dependency].add(source)
    ready = [reference for reference, count in remaining_dependencies.items() if count == 0]
    dependency_depth = {reference: 1 for reference in graph}
    visited_count = 0
    while ready:
        resolved = ready.pop()
        visited_count += 1
        for dependent in dependents[resolved]:
            dependency_depth[dependent] = max(
                dependency_depth[dependent], dependency_depth[resolved] + 1
            )
            if dependency_depth[dependent] > max_dependency_depth:
                raise FormulaError(
                    f"Formula dependency depth exceeds the {max_dependency_depth}-formula limit"
                )
            remaining_dependencies[dependent] -= 1
            if remaining_dependencies[dependent] == 0:
                ready.append(dependent)
    if visited_count != len(graph):
        cycle_reference = next(
            reference for reference, count in remaining_dependencies.items() if count > 0
        )
        raise FormulaError(f"Formula dependency cycle detected at {cycle_reference}")


FormulaTransform = Literal["unwrap_outer_if_then", "unwrap_outer_if_else"]


def transform_formula(formula: str, operation: FormulaTransform) -> str:
    """Apply one allowlisted structural edit to a parsed, existing formula."""

    ast = Parser(formula).parse()
    if ast[0] != "call" or ast[1] != "IF" or len(ast[2]) != 3:
        raise FormulaError("Structural unwrap requires an outer IF with three arguments")
    branch = ast[2][1] if operation == "unwrap_outer_if_then" else ast[2][2]
    transformed = "=" + _render_ast(branch)
    Parser(transformed).parse()
    return transformed


def _render_ast(ast: Any) -> str:
    kind = ast[0]
    if kind == "literal":
        value = ast[1]
        if isinstance(value, Decimal):
            if value == value.to_integral_value():
                return str(int(value))
            return format(value.normalize(), "f")
        if isinstance(value, str):
            return '"' + value.replace('"', '""') + '"'
        raise FormulaError(f"Unsupported literal for formula rendering: {value!r}")
    if kind == "cell":
        return _render_reference(ast[1])
    if kind == "range":
        return f"{_render_reference(ast[1])}:{_render_reference(ast[2], inherit_sheet=True)}"
    if kind == "unary":
        return f"{ast[1]}({_render_ast(ast[2])})"
    if kind == "binary":
        return f"({_render_ast(ast[2])}{ast[1]}{_render_ast(ast[3])})"
    if kind == "call":
        return f"{ast[1]}({','.join(_render_ast(item) for item in ast[2])})"
    raise FormulaError(f"Unsupported AST node for formula rendering: {kind}")


def _render_reference(reference: str, *, inherit_sheet: bool = False) -> str:
    if "!" not in reference:
        return reference
    sheet, cell = reference.split("!", 1)
    if inherit_sheet:
        return cell
    rendered_sheet = f"'{sheet}'" if " " in sheet else sheet
    return f"{rendered_sheet}!{cell}"


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


def _comparison_result(left: Any, right: Any, operator: str) -> bool:
    if left is None:
        left = "" if isinstance(right, str) else False if isinstance(right, bool) else Decimal(0)
    if right is None:
        right = "" if isinstance(left, str) else False if isinstance(left, bool) else Decimal(0)

    def rank(value: Any) -> int:
        if isinstance(value, bool):
            return 2
        if isinstance(value, str):
            return 1
        return 0

    left_rank, right_rank = rank(left), rank(right)
    if left_rank != right_rank:
        comparable_left: Any = left_rank
        comparable_right: Any = right_rank
    elif left_rank == 2:
        comparable_left, comparable_right = bool(left), bool(right)
    elif left_rank == 1:
        comparable_left, comparable_right = left.casefold(), right.casefold()
    else:
        comparable_left, comparable_right = _number(left), _number(right)
    return bool(
        {
            "=": comparable_left == comparable_right,
            "<>": comparable_left != comparable_right,
            "<": comparable_left < comparable_right,
            ">": comparable_left > comparable_right,
            "<=": comparable_left <= comparable_right,
            ">=": comparable_left >= comparable_right,
        }[operator]
    )


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
            return _comparison_result(left, right, op)
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
        if name == "COUNTIF":
            if len(args) != 2 or args[0][0] != "range" or args[1][0] == "range":
                raise FormulaError("COUNTIF requires a range and one equality criterion")
            range_values = [resolve_cell(cell) for cell in _expand_range(args[0][1], args[0][2])]
            criterion = evaluate_ast(args[1], resolve_cell)
            if isinstance(criterion, str):
                if any(marker in criterion for marker in ("*", "?")) or criterion.startswith(
                    ("<", ">", "=")
                ):
                    raise FormulaError("COUNTIF accepts only literal equality criteria")
                expected_text = criterion.casefold()
                return sum(
                    1
                    for value in range_values
                    if ("" if value is None else str(value)).casefold() == expected_text
                )
            expected_number = _number(criterion)
            matches = 0
            for value in range_values:
                if isinstance(value, str):
                    continue
                try:
                    matches += _number(value) == expected_number
                except FormulaError:
                    continue
            return matches
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


def referenced_cells(formula: str, *, max_references: int | None = None) -> list[str]:
    references: set[str] = set()

    def add(reference: str) -> None:
        references.add(reference)
        if max_references is not None and len(references) > max_references:
            raise FormulaError("Formula reference expansion exceeds the configured safety limit")

    def visit(ast: Any) -> None:
        if ast[0] == "cell":
            add(ast[1])
        elif ast[0] == "range":
            for reference in _expand_range(ast[1], ast[2]):
                add(reference)
        elif ast[0] == "binary":
            visit(ast[2])
            visit(ast[3])
        elif ast[0] == "unary":
            visit(ast[2])
        elif ast[0] == "call":
            for argument in ast[2]:
                visit(argument)

    try:
        visit(Parser(formula).parse())
    except RecursionError as exc:
        raise FormulaError("Formula nesting exceeds the parser safety limit") from exc
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


def normalize_override_value(value: Any) -> Any:
    """Decode explicit typed sandbox values without guessing from string shape."""

    if not isinstance(value, Mapping):
        return value
    if set(value) != {"kind", "value"} or value.get("kind") != "date":
        raise FormulaError("Object overrides must use the tagged date value format")
    date_value = value.get("value")
    if not isinstance(date_value, str) or ISO_DATE_RE.fullmatch(date_value) is None:
        raise FormulaError("Tagged date overrides require a YYYY-MM-DD value")
    try:
        return excel_serial(date_value)
    except ValueError as exc:
        raise FormulaError("Tagged date override is not a valid calendar date") from exc


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
    *,
    active_sheet: str | None = None,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    values = {key.upper(): value for key, value in raw_values.items()}
    for key, value in (overrides or {}).items():
        values[key.upper()] = normalize_override_value(value)
    memo: dict[str, Any] = {}
    canonical_formulas = {cell.upper(): formula for cell, formula in formulas.items()}
    active_prefix = f"{active_sheet.upper()}!" if active_sheet is not None else None
    dependencies: dict[str, list[str]] = {}
    for cell, formula in canonical_formulas.items():
        dependencies[cell] = [
            reference[len(active_prefix) :]
            if active_prefix is not None and reference.startswith(active_prefix)
            else reference
            for reference in referenced_cells(formula)
        ]
    formula_dependencies: dict[str, set[str]] = {}
    dependents: dict[str, set[str]] = {cell: set() for cell in canonical_formulas}
    for cell, references in dependencies.items():
        source_sheet = cell.rsplit("!", 1)[0] if "!" in cell else None
        resolved_dependencies: set[str] = set()
        for reference in references:
            canonical_reference = reference.upper()
            if (
                source_sheet is None
                and active_prefix is not None
                and canonical_reference.startswith(active_prefix)
            ):
                canonical_reference = canonical_reference.split("!", 1)[1]
            if "!" not in canonical_reference and source_sheet is not None:
                canonical_reference = f"{source_sheet}!{canonical_reference}"
            if canonical_reference in canonical_formulas:
                resolved_dependencies.add(canonical_reference)
                dependents[canonical_reference].add(cell)
        formula_dependencies[cell] = resolved_dependencies

    remaining = {cell: len(items) for cell, items in formula_dependencies.items()}
    ready = [cell for cell, count in remaining.items() if count == 0]
    while ready:
        cell = ready.pop()
        source_sheet = cell.rsplit("!", 1)[0] if "!" in cell else None

        def resolve(
            reference: str,
            current_sheet: str | None = source_sheet,
            current_cell: str = cell,
        ) -> Any:
            canonical_reference = reference.upper()
            if (
                current_sheet is None
                and active_prefix is not None
                and canonical_reference.startswith(active_prefix)
            ):
                canonical_reference = canonical_reference.split("!", 1)[1]
            if "!" not in canonical_reference and current_sheet is not None:
                canonical_reference = f"{current_sheet}!{canonical_reference}"
            if canonical_reference in canonical_formulas:
                if canonical_reference not in memo:
                    raise FormulaError(
                        "Formula dependency was not resolved before "
                        f"{current_cell}: {canonical_reference}"
                    )
                return memo[canonical_reference]
            return values.get(canonical_reference)

        try:
            memo[cell] = evaluate_ast(Parser(canonical_formulas[cell]).parse(), resolve)
        except RecursionError as exc:
            raise FormulaError("Formula execution nesting exceeds the safety limit") from exc
        for dependent in dependents[cell]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                ready.append(dependent)
    if len(memo) != len(canonical_formulas):
        cycle = next(cell for cell, count in remaining.items() if count > 0)
        raise FormulaError(f"Circular reference at {cycle}")
    return {cell: json_value(value) for cell, value in memo.items()}, dependencies
