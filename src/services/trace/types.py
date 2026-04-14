from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    duration_ms: float = 0.0
    is_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "result": str(self.result) if self.result is not None else None,
            "duration_ms": self.duration_ms,
            "is_error": self.is_error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCallRecord:
        return cls(
            name=data["name"],
            arguments=data.get("arguments", {}),
            result=data.get("result"),
            duration_ms=data.get("duration_ms", 0.0),
            is_error=data.get("is_error", False),
        )


@dataclass
class ExecutionTrace:
    trace_id: str
    request_id: str = ""
    session_id: str = ""
    timestamp: str = ""
    duration_ms: float = 0.0
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    status: str = "success"
    error: str = ""
    request_preview: str = ""
    response_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "model": self.model,
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "status": self.status,
            "error": self.error,
            "request_preview": self.request_preview,
            "response_preview": self.response_preview,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionTrace:
        tool_calls = [
            ToolCallRecord.from_dict(tc) for tc in data.get("tool_calls", [])
        ]
        return cls(
            trace_id=data["trace_id"],
            request_id=data.get("request_id", ""),
            session_id=data.get("session_id", ""),
            timestamp=data.get("timestamp", ""),
            duration_ms=data.get("duration_ms", 0.0),
            model=data.get("model", ""),
            provider=data.get("provider", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            tool_calls=tool_calls,
            status=data.get("status", "success"),
            error=data.get("error", ""),
            request_preview=data.get("request_preview", ""),
            response_preview=data.get("response_preview", ""),
        )
