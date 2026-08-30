"""Probe live NIM models for the minimum ClauseGrid tool-call contract."""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from openai import OpenAI


def probe(model: str, base_url: str, timeout: float) -> dict[str, Any]:
    client = OpenAI(
        base_url=base_url,
        api_key=os.environ["NVIDIA_NIM_API_KEY"],
        timeout=timeout,
        max_retries=0,
    )
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Select the required tool. Return no prose.",
                },
                {"role": "user", "content": "Add 17 and 25."},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "add_numbers",
                        "description": "Add two integers.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "integer"},
                                "b": {"type": "integer"},
                            },
                            "required": ["a", "b"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": "add_numbers"}},
            parallel_tool_calls=False,
            temperature=0,
            max_tokens=128,
        )
        calls = response.choices[0].message.tool_calls or []
        arguments = json.loads(calls[0].function.arguments) if calls else None
        return {
            "model": model,
            "status": "PASS" if arguments == {"a": 17, "b": 25} else "FAIL",
            "tool_call": bool(calls),
            "arguments_ok": arguments == {"a": 17, "b": 25},
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:  # noqa: BLE001 - probe reports only safe metadata
        return {
            "model": model,
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "status_code": getattr(exc, "status_code", None),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+")
    parser.add_argument("--base-url", default="https://integrate.api.nvidia.com/v1")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if not os.environ.get("NVIDIA_NIM_API_KEY"):
        raise SystemExit("NVIDIA_NIM_API_KEY is unset")
    for model in args.models:
        print(json.dumps(probe(model, args.base_url, args.timeout), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
