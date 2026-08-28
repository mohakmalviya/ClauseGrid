"""Process-isolated entry point for one repair workflow invocation."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("method", choices=("baseline", "advanced"))
    parser.add_argument("workbook", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("--reviewer", required=True)
    args = parser.parse_args(argv)

    if args.method == "advanced":
        from .advanced import run_advanced

        runner = run_advanced
    else:
        from .baseline import run_baseline

        runner = run_baseline
    from .path_guard import restrict_file_access

    worker_temp = (args.artifacts / "worker-tmp").resolve()
    worker_temp.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = str(worker_temp)
    os.environ["TMP"] = str(worker_temp)
    tempfile.tempdir = str(worker_temp)
    restrict_file_access(
        readable_files=(args.workbook.resolve(), args.policy.resolve()),
        writable_roots=(args.artifacts.resolve(),),
    )
    result = runner(args.workbook, args.policy, args.artifacts, args.reviewer)
    print(json.dumps(result.to_dict(), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
