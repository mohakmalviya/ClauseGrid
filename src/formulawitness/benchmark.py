"""Deprecated public benchmark compatibility exports.

Held-out cases intentionally live outside the installed repair package under
``evals/sealed``.
"""

from .public_benchmark import (
    DEFAULT_INPUTS,
    DEFECT_FAMILIES,
    MAX_PATCH_CELLS,
    WORKBOOK_CASES,
    visible_cases,
)

__all__ = [
    "DEFAULT_INPUTS",
    "DEFECT_FAMILIES",
    "MAX_PATCH_CELLS",
    "WORKBOOK_CASES",
    "visible_cases",
]
