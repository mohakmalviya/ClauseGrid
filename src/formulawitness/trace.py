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
    def __init__(self, path: Path, run_id: str, *, resume: bool = False):
        self.path = path
        self.run_id = run_id
        self.sequence = 0
        self.previous_event_hash: str | None = None
        path.parent.mkdir(parents=True, exist_ok=True)
        if resume and path.is_file():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
            if lines:
                verify_trajectory(path)
                last = json.loads(lines[-1])
                if last.get("run_id") != run_id:
                    raise ValueError("Trajectory run identifier mismatch")
                self.sequence = int(last["sequence"])
                self.previous_event_hash = str(last["event_hash"])
        else:
            path.write_text("", encoding="utf-8", newline="\n")

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
            "actor": actor,
            "event_type": event_type,
            "input_hash": object_hash(inputs),
            "output_hash": object_hash(outputs),
            "artifact_refs": artifact_refs or [],
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_ms": elapsed_ms,
        }
        event_hash = object_hash({"previous_event_hash": self.previous_event_hash, "event": event})
        event = {
            **event,
            "previous_event_hash": self.previous_event_hash,
            "event_hash": event_hash,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
        self.previous_event_hash = event_hash


def verify_trajectory(path: Path) -> dict[str, str | int]:
    """Verify the deterministic event chain in a JSONL trajectory."""

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not events:
        raise ValueError("Trajectory is empty")
    run_id = str(events[0]["run_id"])
    previous: str | None = None
    for expected_sequence, event in enumerate(events, start=1):
        if event.get("run_id") != run_id or event.get("sequence") != expected_sequence:
            raise ValueError("Trajectory sequence or run identifier mismatch")
        chained_event = {
            key: event[key]
            for key in (
                "schema_version",
                "run_id",
                "sequence",
                "actor",
                "event_type",
                "input_hash",
                "output_hash",
                "artifact_refs",
                "timestamp",
                "elapsed_ms",
            )
        }
        expected_hash = object_hash({"previous_event_hash": previous, "event": chained_event})
        if event.get("previous_event_hash") != previous or event.get("event_hash") != expected_hash:
            raise ValueError(f"Trajectory hash mismatch at sequence {expected_sequence}")
        previous = expected_hash
    return {"run_id": run_id, "event_count": len(events), "final_event_hash": previous or ""}
