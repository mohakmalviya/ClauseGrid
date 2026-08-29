"""Provider-neutral types for model-directed FormulaWitness agents.

These records describe only observable messages, tool calls, and usage. They do not
store or request hidden model reasoning.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


class AgentRecord(BaseModel):
    """Strict immutable base class for values crossing the model boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolSpec(AgentRecord):
    """OpenAI-compatible function tool declaration with a JSON Schema input."""

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    description: str = Field(min_length=1, max_length=4096)
    parameters: dict[str, JsonValue]

    @field_validator("parameters")
    @classmethod
    def require_object_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if value.get("type") != "object":
            raise ValueError("Tool parameters must be a JSON Schema object")
        return value


class ToolCall(AgentRecord):
    """A normalized function call selected by the model."""

    call_id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    arguments: dict[str, JsonValue]


class SystemMessage(AgentRecord):
    role: Literal["system"] = "system"
    content: str = Field(min_length=1)


class UserMessage(AgentRecord):
    role: Literal["user"] = "user"
    content: str = Field(min_length=1)


class AssistantMessage(AgentRecord):
    role: Literal["assistant"] = "assistant"
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()

    @model_validator(mode="after")
    def require_observable_output(self) -> AssistantMessage:
        if not self.content and not self.tool_calls:
            raise ValueError("Assistant message requires content or at least one tool call")
        return self


class ToolResultMessage(AgentRecord):
    role: Literal["tool"] = "tool"
    tool_call_id: str = Field(min_length=1, max_length=256)
    content: str
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


ChatMessage = Annotated[
    SystemMessage | UserMessage | AssistantMessage | ToolResultMessage,
    Field(discriminator="role"),
]


class NamedToolChoice(AgentRecord):
    """Force the model to select one named function tool."""

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


ToolChoice = Literal["auto", "none", "required"] | NamedToolChoice


class ModelRequest(AgentRecord):
    """One bounded chat-completion request."""

    messages: tuple[ChatMessage, ...]
    tools: tuple[ToolSpec, ...] = ()
    tool_choice: ToolChoice = "auto"
    parallel_tool_calls: bool = False
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=131_072)
    attempt_limit: int = Field(default=6, ge=1, le=6)
    seed: int | None = None

    @model_validator(mode="after")
    def validate_request(self) -> ModelRequest:
        if not self.messages:
            raise ValueError("A model request requires at least one message")
        if isinstance(self.tool_choice, NamedToolChoice):
            available = {tool.name for tool in self.tools}
            if self.tool_choice.name not in available:
                raise ValueError("Named tool choice must refer to a declared tool")
        if self.tool_choice == "required" and not self.tools:
            raise ValueError("Required tool choice needs at least one declared tool")
        return self


class ModelUsage(AgentRecord):
    """Normalized usage counters reported by a model provider."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    reported_cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ModelTurn(AgentRecord):
    """Observable output from a single successful provider turn."""

    response_id: str | None = None
    request_id: str | None = None
    model: str = Field(min_length=1)
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str | None = None
    usage: ModelUsage = Field(default_factory=ModelUsage)
    elapsed_ms: int = Field(ge=0)
    retry_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def require_observable_output(self) -> ModelTurn:
        if not self.content and not self.tool_calls:
            raise ValueError("Model turn requires content or at least one tool call")
        return self

    def as_assistant_message(self) -> AssistantMessage:
        """Convert this turn into the assistant message used by the next tool loop."""

        return AssistantMessage(content=self.content, tool_calls=self.tool_calls)
