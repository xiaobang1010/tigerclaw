"""调度类型定义。

参考 OpenClaw 的实现，支持三种调度类型：
- at: 指定时间点执行
- every: 间隔执行（支持毫秒级）
- cron: Cron 表达式（支持时区和 stagger）

会话目标类型：
- main: 主会话执行
- isolated: 隔离会话执行（每次创建新会话）
- current: 当前会话执行
- session:${id}: 指定会话执行
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ScheduleKind(StrEnum):
    """调度类型枚举。"""

    AT = "at"
    EVERY = "every"
    CRON = "cron"


class AtSchedule(BaseModel):
    """指定时间点执行的调度。

    Attributes:
        kind: 调度类型，固定为 "at"
        at: 执行时间，支持 ISO 8601 格式或毫秒时间戳字符串
    """

    kind: Literal[ScheduleKind.AT] = ScheduleKind.AT
    at: str = Field(..., description="执行时间，ISO 8601 格式或毫秒时间戳")


class EverySchedule(BaseModel):
    """间隔执行的调度。

    Attributes:
        kind: 调度类型，固定为 "every"
        every_ms: 执行间隔（毫秒）
        anchor_ms: 锚定时间点（毫秒时间戳），用于对齐执行时间
    """

    kind: Literal[ScheduleKind.EVERY] = ScheduleKind.EVERY
    every_ms: int = Field(..., ge=1, description="执行间隔（毫秒）")
    anchor_ms: int | None = Field(None, description="锚定时间点（毫秒时间戳）")


class CronSchedule(BaseModel):
    """Cron 表达式调度。

    Attributes:
        kind: 调度类型，固定为 "cron"
        expr: Cron 表达式（5 或 6 字段）
        tz: 时区名称（IANA 时区，如 "Asia/Shanghai"）
        stagger_ms: 随机偏移窗口（毫秒），用于分散负载
    """

    kind: Literal[ScheduleKind.CRON] = ScheduleKind.CRON
    expr: str = Field(..., min_length=1, description="Cron 表达式")
    tz: str | None = Field(None, description="时区名称（IANA 时区）")
    stagger_ms: int | None = Field(None, ge=0, description="随机偏移窗口（毫秒）")


Schedule = Annotated[AtSchedule | EverySchedule | CronSchedule, Field(discriminator="kind")]
"""调度类型联合，通过 kind 字段区分具体类型。"""


class ScheduleState(BaseModel):
    """调度状态。

    Attributes:
        next_run_at_ms: 下次执行时间（毫秒时间戳）
        running_at_ms: 当前执行开始时间（毫秒时间戳）
        last_run_at_ms: 上次执行时间（毫秒时间戳）
        last_run_status: 上次执行状态
        last_error: 上次错误信息
        consecutive_errors: 连续错误次数
        schedule_error_count: 调度计算错误次数
    """

    next_run_at_ms: int | None = None
    running_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_run_status: str | None = None
    last_error: str | None = None
    consecutive_errors: int = 0
    schedule_error_count: int = 0


class TaskDefinitionV2(BaseModel):
    """任务定义 V2。

    使用新的调度类型系统。
    """

    id: str = Field(..., description="任务ID")
    name: str = Field(..., description="任务名称")
    schedule: Schedule = Field(..., description="调度配置")
    handler: str = Field(..., description="处理函数路径")
    params: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, description="任务参数"
    )
    enabled: bool = Field(default=True, description="是否启用")
    max_retries: int = Field(default=3, ge=0, description="最大重试次数")
    timeout: int = Field(default=300, ge=1, description="超时时间（秒）")
    state: ScheduleState = Field(default_factory=ScheduleState, description="调度状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")


SESSION_ID_PATTERN = re.compile(r"^session:(.+)$")


class SessionTargetKind(StrEnum):
    """会话目标类型枚举。"""

    MAIN = "main"
    ISOLATED = "isolated"
    CURRENT = "current"
    SESSION_ID = "session_id"


@dataclass
class ResolvedSessionTarget:
    """解析后的会话目标。

    Attributes:
        kind: 会话目标类型
        session_id: 会话ID（仅 session_id 类型有值）
        is_isolated: 是否为隔离会话（需要创建新会话）
        force_new: 是否强制创建新会话
    """

    kind: SessionTargetKind
    session_id: str | None = None
    is_isolated: bool = False
    force_new: bool = False


SessionTarget = Literal["main", "isolated", "current"] | Annotated[str, Field(pattern=r"^session:.+$")]
"""会话目标类型。

支持以下值：
- "main": 主会话执行
- "isolated": 隔离会话执行（每次创建新会话）
- "current": 当前会话执行
- "session:${id}": 指定会话执行
"""


class SessionTargetResolver:
    """会话目标解析器。

    将会话目标字符串解析为具体的执行配置。
    """

    @staticmethod
    def parse(target: str) -> ResolvedSessionTarget:
        """解析会话目标字符串。

        Args:
            target: 会话目标字符串

        Returns:
            解析后的会话目标

        Raises:
            ValueError: 无效的会话目标格式
        """
        if target == "main":
            return ResolvedSessionTarget(
                kind=SessionTargetKind.MAIN,
                is_isolated=False,
                force_new=False,
            )

        if target == "isolated":
            return ResolvedSessionTarget(
                kind=SessionTargetKind.ISOLATED,
                is_isolated=True,
                force_new=True,
            )

        if target == "current":
            return ResolvedSessionTarget(
                kind=SessionTargetKind.CURRENT,
                is_isolated=False,
                force_new=False,
            )

        match = SESSION_ID_PATTERN.match(target)
        if match:
            session_id = match.group(1).strip()
            if not session_id:
                raise ValueError(f"无效的会话目标格式: {target}，session ID 不能为空")
            return ResolvedSessionTarget(
                kind=SessionTargetKind.SESSION_ID,
                session_id=session_id,
                is_isolated=False,
                force_new=False,
            )

        raise ValueError(
            f"无效的会话目标格式: {target}，"
            f"支持的格式: main, isolated, current, session:${{id}}"
        )

    @staticmethod
    def validate(target: str) -> bool:
        """验证会话目标格式是否有效。

        Args:
            target: 会话目标字符串

        Returns:
            是否有效
        """
        try:
            SessionTargetResolver.parse(target)
            return True
        except ValueError:
            return False


class CronSessionConfig(BaseModel):
    """Cron 会话配置。

    Attributes:
        session_key: 会话键（用于持久化）
        session_target: 会话目标类型
        agent_id: 代理ID
        timeout_ms: 会话超时时间（毫秒）
        idle_timeout_ms: 空闲超时时间（毫秒）
    """

    session_key: str = Field(..., description="会话键")
    session_target: str = Field(default="isolated", description="会话目标类型")
    agent_id: str = Field(default="main", description="代理ID")
    timeout_ms: int = Field(default=300000, ge=1000, description="会话超时时间（毫秒）")
    idle_timeout_ms: int = Field(
        default=3600000, ge=60000, description="空闲超时时间（毫秒）"
    )

    def resolve_target(self) -> ResolvedSessionTarget:
        """解析会话目标。"""
        return SessionTargetResolver.parse(self.session_target)

    def generate_session_id(self) -> str:
        """生成新的会话ID。"""
        return str(uuid.uuid4())


class CronRunOutcome(BaseModel):
    """Cron 运行结果。

    Attributes:
        status: 运行状态
        error: 错误信息
        summary: 执行摘要
        session_id: 会话ID
        session_key: 会话键
    """

    status: Literal["ok", "error", "skipped"] = Field(..., description="运行状态")
    error: str | None = Field(None, description="错误信息")
    summary: str | None = Field(None, description="执行摘要")
    session_id: str | None = Field(None, description="会话ID")
    session_key: str | None = Field(None, description="会话键")
