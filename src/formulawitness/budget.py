"""Shared fairness budget for the compared repair workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import JsonValue


@dataclass(frozen=True)
class RunBudget:
    """Identical model and execution limits supplied to both systems."""

    model_id: str = "deterministic-offline-v1"
    token_limit: int = 0
    workbook_case_execution_limit: int = 160


@dataclass
class BudgetLedger:
    budget: RunBudget
    workbook_case_executions_used: int = 0

    def charge_cases(self, count: int) -> None:
        proposed = self.workbook_case_executions_used + count
        if proposed > self.budget.workbook_case_execution_limit:
            raise RuntimeError(
                "Workbook execution budget exceeded: "
                f"{proposed}>{self.budget.workbook_case_execution_limit}"
            )
        self.workbook_case_executions_used = proposed

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            **asdict(self.budget),
            "tokens_used": 0,
            "workbook_case_executions_used": self.workbook_case_executions_used,
        }


DEFAULT_RUN_BUDGET = RunBudget()
