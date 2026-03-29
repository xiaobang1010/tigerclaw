"""模型故障转移类型定义。

本模块定义了模型故障转移相关的数据类型，
包括尝试记录、候选模型和结果封装。
"""

from dataclasses import dataclass, field
from typing import Any

from agents.failover_reason import FailoverReason


@dataclass
class FallbackAttempt:
    """故障转移尝试记录。

    记录单次模型调用的尝试信息，包括错误详情。

    Attributes:
        provider: 模型提供商名称
        model: 模型标识符
        error: 错误消息
        reason: 故障转移原因（可选）
        status: HTTP 状态码（可选）
        code: 错误码（可选）
    """

    provider: str
    model: str
    error: str
    reason: FailoverReason | None = None
    status: int | None = None
    code: str | None = None


@dataclass
class ModelCandidate:
    """候选模型。

    表示一个可用于故障转移的模型候选。

    Attributes:
        provider: 模型提供商名称
        model: 模型标识符
    """

    provider: str
    model: str


@dataclass
class ModelFallbackResult:
    """模型故障转移结果。

    封装故障转移执行的最终结果，包括成功的返回值和所有尝试记录。

    Attributes:
        result: 成功时的返回值
        provider: 最终成功的提供商名称
        model: 最终成功的模型标识符
        attempts: 所有尝试记录列表
    """

    result: Any
    provider: str
    model: str
    attempts: list[FallbackAttempt] = field(default_factory=list)
