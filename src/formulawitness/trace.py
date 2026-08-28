"""Append-only trajectory logging with stable input and output hashes."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def object_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class Trajectory:
    def __init__(self, path: Path, run_id: str):
        self.path = path
        self.run_id = run_id
        self.sequence = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def record(
        self,
        actor: str,
        event_type: str,
        inputs: Any,
        outputs: Any,
        *,
        elapsed_ms: int = 0,
        artifact_refs: list[str] | None = None,
    ) -> None:
        self.sequence += 1
        event = {
            "schema_version": 1,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "event_type": event_type,
            "input_hash": object_hash(inputs),
            "output_hash": object_hash(outputs),
            "elapsed_ms": elapsed_ms,
            "artifact_refs": artifact_refs or [],
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
