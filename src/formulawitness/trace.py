"""Append-only trajectory logging with stable input and output hashes."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SECRET_FIELD = re.compile(
    r"(?:^|_)(?:api_?key|authorization|credential|password|secret)(?:$|_)", re.IGNORECASE
)
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def redact_secrets(value: Any) -> Any:
    """Return a JSON-compatible copy with common credential fields removed."""

    if isinstance(value, dict):
        return {
            str(key): ("[REDACTED]" if _SECRET_FIELD.search(str(key)) else redact_secrets(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _BEARER_VALUE.sub("Bearer [REDACTED]", value)
    return value


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
        instruction: str,
        tool: str,
        input_summary: Any,
        output_summary: Any,
        feedback: str,
        retry_count: int = 0,
        elapsed_ms: int = 0,
        artifact_refs: list[str] | None = None,
    ) -> None:
        if (
            not actor.strip()
            or not event_type.strip()
            or not instruction.strip()
            or not tool.strip()
        ):
            raise ValueError("Trajectory events require actor, event, instruction, and tool")
        if not feedback.strip() or retry_count < 0:
            raise ValueError("Trajectory events require feedback and a nonnegative retry count")
        self.sequence += 1
        event = {
            "schema_version": 2,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "actor": actor,
            "event_type": event_type,
            "instruction": instruction,
            "tool": tool,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "feedback": feedback,
            "retry_count": retry_count,
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

    def record_agent_event(
        self,
        actor: str,
        event_type: str,
        payload: Any,
        *,
        model_id: str,
        prompt_version: str,
        finish_reason: str | None = None,
        usage: dict[str, int | float | None] | None = None,
        elapsed_ms: int = 0,
        retry_count: int = 0,
    ) -> None:
        """Append an observable model/tool/state event without hidden reasoning or secrets."""

        if not actor.strip() or not event_type.strip() or not model_id.strip():
            raise ValueError("Agent trace events require actor, event type, and model id")
        if not prompt_version.strip() or retry_count < 0 or elapsed_ms < 0:
            raise ValueError("Agent trace metadata is invalid")
        self.sequence += 1
        event = {
            "schema_version": 3,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "actor": actor,
            "event_type": event_type,
            "payload": redact_secrets(payload),
            "model_id": model_id,
            "prompt_version": prompt_version,
            "finish_reason": finish_reason,
            "usage": usage or {},
            "retry_count": retry_count,
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
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("Trajectory events must be JSON objects")
    run_id = str(events[0]["run_id"])
    if not run_id.strip():
        raise ValueError("Trajectory run identifier is empty")
    previous: str | None = None
    for expected_sequence, event in enumerate(events, start=1):
        if event.get("run_id") != run_id or event.get("sequence") != expected_sequence:
            raise ValueError("Trajectory sequence or run identifier mismatch")
        version = event.get("schema_version")
        fields = [
            "schema_version",
            "run_id",
            "sequence",
            "actor",
            "event_type",
        ]
        if version == 2:
            fields.extend(
                [
                    "instruction",
                    "tool",
                    "input_summary",
                    "output_summary",
                    "feedback",
                    "retry_count",
                ]
            )
        elif version == 3:
            fields.extend(
                [
                    "payload",
                    "model_id",
                    "prompt_version",
                    "finish_reason",
                    "usage",
                    "retry_count",
                ]
            )
        elif version != 1:
            raise ValueError(f"Unsupported trajectory schema version: {version}")
        if version in {1, 2}:
            fields.extend(["input_hash", "output_hash", "artifact_refs"])
        fields.extend(["timestamp", "elapsed_ms"])
        expected_fields = set(fields) | {"previous_event_hash", "event_hash"}
        actual_fields = set(event)
        if actual_fields != expected_fields:
            missing = sorted(expected_fields - actual_fields)
            unknown = sorted(actual_fields - expected_fields)
            details = []
            if missing:
                details.append(f"missing={missing}")
            if unknown:
                details.append(f"unknown={unknown}")
            raise ValueError("Trajectory fields do not match the schema: " + ", ".join(details))
        try:
            chained_event = {key: event[key] for key in fields}
        except KeyError as exc:
            raise ValueError(f"Trajectory field missing: {exc.args[0]}") from exc
        event_hash = event.get("event_hash")
        prior_hash = event.get("previous_event_hash")
        if not isinstance(event_hash, str) or re.fullmatch(r"[0-9a-f]{64}", event_hash) is None:
            raise ValueError(f"Trajectory event hash is invalid at sequence {expected_sequence}")
        if prior_hash is not None and (
            not isinstance(prior_hash, str) or re.fullmatch(r"[0-9a-f]{64}", prior_hash) is None
        ):
            raise ValueError(f"Trajectory previous hash is invalid at sequence {expected_sequence}")
        expected_hash = object_hash({"previous_event_hash": previous, "event": chained_event})
        if prior_hash != previous or event_hash != expected_hash:
            raise ValueError(f"Trajectory hash mismatch at sequence {expected_sequence}")
        previous = expected_hash
    return {"run_id": run_id, "event_count": len(events), "final_event_hash": previous or ""}
