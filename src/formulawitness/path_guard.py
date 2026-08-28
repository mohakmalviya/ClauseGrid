"""Narrow process-local file capability guard for deterministic repair workers."""

from __future__ import annotations

import builtins
import io
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, cast


class FileCapabilityError(PermissionError):
    pass


def _resolved(path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> Path:
    return Path(os.fsdecode(path)).resolve(strict=False)


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def restrict_file_access(
    *,
    readable_files: Iterable[Path],
    writable_roots: Iterable[Path],
) -> None:
    """Restrict ordinary Python file opens to explicit inputs and output roots.

    The repair code is fixed and does not receive arbitrary Python execution. This
    guard removes ambient file-read capability from that process; it is not a
    substitute for a hostile-code kernel sandbox.
    """

    readable = {_resolved(path) for path in readable_files}
    writable = {_resolved(path) for path in writable_roots}
    original_builtin_open = builtins.open
    original_io_open = io.open
    original_os_open = os.open

    def check(path: Any, *, write: bool) -> None:
        if isinstance(path, int):
            return
        resolved = _resolved(path)
        if any(_within(resolved, root) for root in writable):
            return
        if not write and resolved in readable:
            return
        raise FileCapabilityError(f"File capability denied: {resolved.name}")

    def guarded_open(
        opener: Callable[..., Any],
        file: Any,
        mode: str = "r",
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        check(file, write=any(flag in mode for flag in "wax+"))
        return opener(file, mode, *args, **kwargs)

    def builtin_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        return guarded_open(original_builtin_open, file, mode, *args, **kwargs)

    def io_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        return guarded_open(original_io_open, file, mode, *args, **kwargs)

    def os_open(file: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
        check(file, write=bool(flags & write_flags))
        return original_os_open(file, flags, mode, dir_fd=dir_fd)

    builtins.open = builtin_open
    io.open = io_open
    os.open = cast(Any, os_open)
