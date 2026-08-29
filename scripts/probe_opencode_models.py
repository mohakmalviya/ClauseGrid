"""Probe current OpenCode Zen free models for FormulaWitness's tool-call contract."""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from openai import OpenAI

DEFAULT_FREE_MODELS = (
    "big-pickle",
    "deepseek-v4-flash-free",
    "hy3-free",
    "laguna-s-2.1-free",
    "ling-3.0-flash-fin-free",
    "nemotron-3-ultra-free",
    "nemotron-3.5-lightning-free",
)


def probe(client: OpenAI, model: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Select the required tool. Return no prose."},
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
    except Exception as exc:  # noqa: BLE001 - probe reports safe metadata only
        return {
            "model": model,
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "status_code": getattr(exc, "status_code", None),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="*", default=DEFAULT_FREE_MODELS)
    parser.add_argument("--base-url", default="https://opencode.ai/zen/v1")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    api_key = os.environ.get("OPENCODE_API_KEY")
    if not api_key:
        raise SystemExit("OPENCODE_API_KEY is unset")
    client = OpenAI(
        base_url=args.base_url,
        api_key=api_key,
        timeout=args.timeout,
        max_retries=0,
    )
    try:
        available = {item.id for item in client.models.list().data}
        for model in args.models:
            if model not in available:
                print(json.dumps({"model": model, "status": "NOT_LISTED"}, sort_keys=True))
                continue
            print(json.dumps(probe(client, model), sort_keys=True))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
