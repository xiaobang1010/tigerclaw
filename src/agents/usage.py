from dataclasses import dataclass
from typing import Any


@dataclass
class NormalizedUsage:
    """标准化后的使用量数据"""

    input: int | None = None
    output: int | None = None
    cache_read: int | None = None
    cache_write: int | None = None
    total: int | None = None


@dataclass
class UsageSnapshot:
    """使用量快照，用于累计统计"""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total_tokens: int = 0
    cost: dict[str, float] | None = None

    def __post_init__(self):
        if self.cost is None:
            self.cost = {
                "input": 0.0,
                "output": 0.0,
                "cache_read": 0.0,
                "cache_write": 0.0,
                "total": 0.0,
            }


def _as_finite_number(value: Any) -> int | None:
    """将值转换为有效的有限数字"""
    if not isinstance(value, (int, float)):
        return None
    if not isinstance(value, int):
        if not float("-inf") < value < float("inf"):
            return None
        return int(value)
    return value


def normalize_usage(raw: dict[str, Any] | None) -> NormalizedUsage | None:
    """
    将各种格式的 usage 数据标准化为 NormalizedUsage

    支持的字段名:
    - input: input, inputTokens, input_tokens, promptTokens, prompt_tokens
    - output: output, outputTokens, output_tokens, completionTokens, completion_tokens
    - cache_read: cacheRead, cache_read, cache_read_input_tokens, cached_tokens, prompt_tokens_details.cached_tokens
    - cache_write: cacheWrite, cache_write, cache_creation_input_tokens
    - total: total, totalTokens, total_tokens
    """
    if not raw:
        return None

    raw_input = _as_finite_number(
        raw.get("input")
        or raw.get("inputTokens")
        or raw.get("input_tokens")
        or raw.get("promptTokens")
        or raw.get("prompt_tokens")
    )
    input_tokens = raw_input if raw_input is not None and raw_input >= 0 else (0 if raw_input is not None else None)

    output = _as_finite_number(
        raw.get("output")
        or raw.get("outputTokens")
        or raw.get("output_tokens")
        or raw.get("completionTokens")
        or raw.get("completion_tokens")
    )

    cache_read = _as_finite_number(
        raw.get("cacheRead")
        or raw.get("cache_read")
        or raw.get("cache_read_input_tokens")
        or raw.get("cached_tokens")
        or (raw.get("prompt_tokens_details", {}).get("cached_tokens") if isinstance(raw.get("prompt_tokens_details"), dict) else None)
    )

    cache_write = _as_finite_number(
        raw.get("cacheWrite") or raw.get("cache_write") or raw.get("cache_creation_input_tokens")
    )

    total = _as_finite_number(raw.get("total") or raw.get("totalTokens") or raw.get("total_tokens"))

    if all(v is None for v in [input_tokens, output, cache_read, cache_write, total]):
        return None

    return NormalizedUsage(
        input=input_tokens,
        output=output,
        cache_read=cache_read,
        cache_write=cache_write,
        total=total,
    )


def make_zero_usage_snapshot() -> UsageSnapshot:
    """创建零值使用量快照"""
    return UsageSnapshot(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=0,
        cost={
            "input": 0.0,
            "output": 0.0,
            "cache_read": 0.0,
            "cache_write": 0.0,
            "total": 0.0,
        },
    )


def has_nonzero_usage(usage: NormalizedUsage | None) -> bool:
    """检查是否有非零使用量"""
    if not usage:
        return False
    return any(
        v is not None and v > 0
        for v in [usage.input, usage.output, usage.cache_read, usage.cache_write, usage.total]
    )


def derive_prompt_tokens(usage: NormalizedUsage | None) -> int | None:
    """
    计算 prompt tokens

    prompt tokens = input + cache_read + cache_write
    """
    if not usage:
        return None
    input_val = usage.input or 0
    cache_read_val = usage.cache_read or 0
    cache_write_val = usage.cache_write or 0
    total = input_val + cache_read_val + cache_write_val
    return total if total > 0 else None
