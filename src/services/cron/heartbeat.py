"""心跳检测策略模块。

参考 OpenClaw 的 heartbeat-policy.ts 实现。
支持心跳超时告警、恢复继续执行和策略配置。
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from loguru import logger

HEARTBEAT_TOKEN = "HEARTBEAT_OK"
HEARTBEAT_PROMPT = (
    "Read HEARTBEAT.md if it exists (workspace context). "
    "Follow it strictly. Do not infer or repeat old tasks from prior chats. "
    "If nothing needs attention, reply HEARTBEAT_OK."
)
DEFAULT_HEARTBEAT_EVERY = "30m"
DEFAULT_HEARTBEAT_ACK_MAX_CHARS = 300


class HeartbeatMode(StrEnum):
    """心跳模式枚举。"""

    HEARTBEAT = "heartbeat"
    MESSAGE = "message"


@dataclass
class HeartbeatConfig:
    """心跳配置。

    Attributes:
        enabled: 是否启用心跳检测
        every: 心跳间隔（如 "30m", "1h"）
        prompt: 心跳提示语
        ack_max_chars: 确认消息最大字符数
        timeout_ms: 心跳超时时间（毫秒）
        failure_alert: 失败告警配置
    """

    enabled: bool = True
    every: str = DEFAULT_HEARTBEAT_EVERY
    prompt: str = HEARTBEAT_PROMPT
    ack_max_chars: int = DEFAULT_HEARTBEAT_ACK_MAX_CHARS
    timeout_ms: int = 60000
    failure_alert: HeartbeatFailureAlert | None = None


@dataclass
class HeartbeatFailureAlert:
    """心跳失败告警配置。

    Attributes:
        after: 连续失败多少次后告警
        channel: 告警渠道
        to: 告警目标地址
        cooldown_ms: 告警冷却时间（毫秒）
        mode: 投递模式
        account_id: 账户 ID
    """

    after: int = 3
    channel: str | None = None
    to: str | None = None
    cooldown_ms: int = 3600000
    mode: str = "announce"
    account_id: str | None = None


@dataclass
class HeartbeatState:
    """心跳状态。

    Attributes:
        last_heartbeat_at_ms: 上次心跳时间戳
        last_success_at_ms: 上次成功时间戳
        consecutive_failures: 连续失败次数
        last_failure_at_ms: 上次失败时间戳
        last_alert_at_ms: 上次告警时间戳
        is_timeout: 是否超时
    """

    last_heartbeat_at_ms: int | None = None
    last_success_at_ms: int | None = None
    consecutive_failures: int = 0
    last_failure_at_ms: int | None = None
    last_alert_at_ms: int | None = None
    is_timeout: bool = False


@dataclass
class StripResult:
    """心跳令牌剥离结果。

    Attributes:
        should_skip: 是否应跳过投递
        text: 处理后的文本
        did_strip: 是否剥离了令牌
    """

    should_skip: bool = False
    text: str = ""
    did_strip: bool = False


def is_heartbeat_content_effectively_empty(content: str | None) -> bool:
    """检查心跳内容是否有效为空。

    如果内容只包含空白、注释行或空行，则视为有效为空。

    Args:
        content: 文件内容

    Returns:
        是否有效为空
    """
    if content is None:
        return False
    if not isinstance(content, str):
        return False

    lines = content.split("\n")
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        if re.match(r"^#+(\s|$)", trimmed):
            continue
        if re.match(r"^[-*+]\s*(\[[\sXx]?\]\s*)?$", trimmed):
            continue
        return False
    return True


def resolve_heartbeat_prompt(raw: str | None) -> str:
    """解析心跳提示语。

    Args:
        raw: 原始提示语

    Returns:
        解析后的提示语
    """
    trimmed = raw.strip() if raw else ""
    return trimmed or HEARTBEAT_PROMPT


def parse_interval(interval: str) -> int:
    """解析时间间隔字符串为毫秒。

    支持格式：
    - 数字 + 单位：30s, 5m, 1h, 2d
    - 纯数字：视为毫秒

    Args:
        interval: 时间间隔字符串

    Returns:
        毫秒数
    """
    if not interval:
        return 0

    interval = interval.strip().lower()
    if not interval:
        return 0

    if interval.isdigit():
        return int(interval)

    match = re.match(r"^(\d+(?:\.\d+)?)\s*(s|sec|m|min|h|hour|d|day)?$", interval)
    if not match:
        return 0

    value = float(match.group(1))
    unit = match.group(2) or "m"

    multipliers = {
        "s": 1000,
        "sec": 1000,
        "m": 60000,
        "min": 60000,
        "h": 3600000,
        "hour": 3600000,
        "d": 86400000,
        "day": 86400000,
    }

    return int(value * multipliers.get(unit, 60000))


def _strip_token_at_edges(raw: str) -> tuple[str, bool]:
    """在文本边缘剥离心跳令牌。

    Args:
        raw: 原始文本

    Returns:
        (处理后的文本, 是否剥离了令牌)
    """
    text = raw.strip()
    if not text:
        return "", False

    token = HEARTBEAT_TOKEN
    token_at_end_pattern = re.compile(rf"{re.escape(token)}[^\w]{{0,4}}$")

    if token not in text:
        return text, False

    did_strip = False
    changed = True

    while changed:
        changed = False
        next_text = text.strip()

        if next_text.startswith(token):
            after = next_text[len(token) :].lstrip()
            text = after
            did_strip = True
            changed = True
            continue

        if token_at_end_pattern.search(next_text):
            idx = next_text.rfind(token)
            before = next_text[:idx].rstrip()
            if not before:
                text = ""
            else:
                after = next_text[idx + len(token) :].lstrip()
                text = f"{before}{after}".rstrip()
            did_strip = True
            changed = True

    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed, did_strip


def strip_heartbeat_token(
    raw: str | None,
    mode: HeartbeatMode = HeartbeatMode.MESSAGE,
    max_ack_chars: int | None = None,
) -> StripResult:
    """剥离心跳令牌。

    Args:
        raw: 原始文本
        mode: 处理模式
        max_ack_chars: 确认消息最大字符数

    Returns:
        剥离结果
    """
    if not raw:
        return StripResult(should_skip=True, text="", did_strip=False)

    trimmed = raw.strip()
    if not trimmed:
        return StripResult(should_skip=True, text="", did_strip=False)

    ack_chars = max_ack_chars if max_ack_chars is not None else DEFAULT_HEARTBEAT_ACK_MAX_CHARS
    ack_chars = max(0, ack_chars)

    def strip_markup(text: str) -> str:
        return (
            re.sub(r"<[^>]*>", " ", text)
            .replace("&nbsp;", " ")
            .replace("&NBSP;", " ")
        )

    trimmed_normalized = strip_markup(trimmed)
    has_token = HEARTBEAT_TOKEN in trimmed or HEARTBEAT_TOKEN in trimmed_normalized

    if not has_token:
        return StripResult(should_skip=False, text=trimmed, did_strip=False)

    stripped_original, did_strip_original = _strip_token_at_edges(trimmed)
    stripped_normalized, did_strip_normalized = _strip_token_at_edges(trimmed_normalized)

    picked_text, picked_did_strip = (
        (stripped_original, did_strip_original)
        if did_strip_original and stripped_original
        else (stripped_normalized, did_strip_normalized)
    )

    if not picked_did_strip:
        return StripResult(should_skip=False, text=trimmed, did_strip=False)

    if not picked_text:
        return StripResult(should_skip=True, text="", did_strip=True)

    rest = picked_text.strip()
    if mode == HeartbeatMode.HEARTBEAT and len(rest) <= ack_chars:
        return StripResult(should_skip=True, text="", did_strip=True)

    return StripResult(should_skip=False, text=rest, did_strip=True)


class HeartbeatPolicy:
    """心跳策略管理器。

    管理心跳检测、超时告警和恢复逻辑。
    """

    def __init__(
        self,
        config: HeartbeatConfig | None = None,
        now_ms_func: Callable[[], int] | None = None,
    ) -> None:
        """初始化心跳策略。

        Args:
            config: 心跳配置
            now_ms_func: 获取当前时间的函数（用于测试）
        """
        self.config = config or HeartbeatConfig()
        self._now_ms = now_ms_func or self._default_now_ms
        self._state = HeartbeatState()

    def _default_now_ms(self) -> int:
        """默认获取当前时间戳。"""
        import time

        return int(time.time() * 1000)

    @property
    def state(self) -> HeartbeatState:
        """获取心跳状态。"""
        return self._state

    def check_timeout(self) -> bool:
        """检查是否心跳超时。

        Returns:
            是否超时
        """
        if not self.config.enabled:
            return False

        now = self._now_ms()
        last = self._state.last_heartbeat_at_ms

        if last is None:
            return False

        elapsed = now - last
        is_timeout = elapsed > self.config.timeout_ms

        if is_timeout and not self._state.is_timeout:
            logger.warning(
                "心跳超时",
                elapsed_ms=elapsed,
                timeout_ms=self.config.timeout_ms,
            )

        self._state.is_timeout = is_timeout
        return is_timeout

    def record_heartbeat(self, success: bool = True) -> None:
        """记录心跳结果。

        Args:
            success: 是否成功
        """
        now = self._now_ms()
        self._state.last_heartbeat_at_ms = now

        if success:
            self._state.last_success_at_ms = now
            self._state.consecutive_failures = 0
            self._state.is_timeout = False
            logger.debug("心跳成功")
        else:
            self._state.consecutive_failures += 1
            self._state.last_failure_at_ms = now
            logger.warning(
                "心跳失败",
                consecutive_failures=self._state.consecutive_failures,
            )

    def should_alert(self) -> bool:
        """判断是否应该发送告警。

        Returns:
            是否应该告警
        """
        if not self.config.failure_alert:
            return False

        alert_config = self.config.failure_alert
        now = self._now_ms()

        if self._state.consecutive_failures < alert_config.after:
            return False

        if self._state.last_alert_at_ms is not None:
            elapsed = now - self._state.last_alert_at_ms
            if elapsed < alert_config.cooldown_ms:
                return False

        return True

    def record_alert(self) -> None:
        """记录告警已发送。"""
        self._state.last_alert_at_ms = self._now_ms()
        logger.info("心跳失败告警已发送")

    def get_next_interval_ms(self) -> int:
        """获取下次心跳间隔。

        Returns:
            间隔毫秒数
        """
        return parse_interval(self.config.every)

    def is_recovered(self) -> bool:
        """检查是否已从超时恢复。

        Returns:
            是否已恢复
        """
        return (
            self._state.is_timeout
            and self._state.last_success_at_ms is not None
            and self._state.last_success_at_ms > (self._state.last_failure_at_ms or 0)
        )

    def reset(self) -> None:
        """重置心跳状态。"""
        self._state = HeartbeatState()
        logger.debug("心跳状态已重置")


def should_skip_heartbeat_only_delivery(
    payloads: list[dict],
    ack_max_chars: int,
) -> bool:
    """判断是否应跳过仅心跳消息的投递。

    Args:
        payloads: 消息负载列表
        ack_max_chars: 确认消息最大字符数

    Returns:
        是否应跳过
    """
    if not payloads:
        return True

    for payload in payloads:
        text = payload.get("text", "")
        if not text:
            continue

        result = strip_heartbeat_token(
            text,
            mode=HeartbeatMode.HEARTBEAT,
            max_ack_chars=ack_max_chars,
        )
        if result.should_skip:
            return True

    return False


def should_enqueue_cron_main_summary(
    summary_text: str | None,
    delivery_requested: bool,
    delivered: bool | None,
    delivery_attempted: bool | None,
    suppress_main_summary: bool,
    is_cron_system_event: Callable[[str], bool],
) -> bool:
    """判断是否应将 Cron 主摘要加入队列。

    Args:
        summary_text: 摘要文本
        delivery_requested: 是否请求投递
        delivered: 是否已投递
        delivery_attempted: 是否尝试过投递
        suppress_main_summary: 是否抑制主摘要
        is_cron_system_event: 判断是否为系统事件的函数

    Returns:
        是否应加入队列
    """
    if not summary_text or not summary_text.strip():
        return False

    if not is_cron_system_event(summary_text):
        return False

    if not delivery_requested:
        return False

    if delivered:
        return False

    if delivery_attempted:
        return False

    return not suppress_main_summary
