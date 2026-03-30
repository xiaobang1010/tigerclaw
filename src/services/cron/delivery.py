"""Cron 消息投递机制。

参考 OpenClaw 的实现，支持三种投递模式：
- none: 不投递
- announce: 投递到消息渠道
- webhook: HTTP POST 投递

支持功能：
- 渠道选择 (last 或指定渠道 ID)
- 多账户支持
- 最佳努力投递模式
- 投递错误处理和日志
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
from loguru import logger

from core.types.sessions import DeliveryContext


class DeliveryMode(StrEnum):
    """投递模式枚举。"""

    NONE = "none"
    ANNOUNCE = "announce"
    WEBHOOK = "webhook"


@dataclass
class Delivery:
    """投递配置。

    Attributes:
        mode: 投递模式
        channel: 目标渠道 (ChannelId 或 "last")
        to: 目标地址
        account_id: 多账户场景下的账户 ID
        best_effort: 是否启用最佳努力投递模式
        failure_destination: 失败告警的目标配置
    """

    mode: DeliveryMode = DeliveryMode.NONE
    channel: str | None = None
    to: str | None = None
    account_id: str | None = None
    best_effort: bool = False
    failure_destination: FailureDestination | None = None


@dataclass
class FailureDestination:
    """失败告警目标配置。

    Attributes:
        channel: 目标渠道 (ChannelId 或 "last")
        to: 目标地址
        account_id: 多账户场景下的账户 ID
        mode: 投递模式 (announce 或 webhook)
    """

    channel: str | None = None
    to: str | None = None
    account_id: str | None = None
    mode: DeliveryMode = DeliveryMode.ANNOUNCE


@dataclass
class DeliveryResult:
    """投递结果。

    Attributes:
        success: 是否成功
        mode: 使用的投递模式
        channel: 实际使用的渠道
        to: 实际投递的目标地址
        message_id: 消息 ID (announce 模式)
        status_code: HTTP 状态码 (webhook 模式)
        error: 错误信息
    """

    success: bool = False
    mode: DeliveryMode = DeliveryMode.NONE
    channel: str | None = None
    to: str | None = None
    message_id: str | None = None
    status_code: int | None = None
    error: str | None = None


@dataclass
class DeliveryPlan:
    """投递计划。

    解析后的投递配置，包含所有必要信息。

    Attributes:
        mode: 投递模式
        channel: 目标渠道
        to: 目标地址
        account_id: 账户 ID
        source: 配置来源 (delivery 或 payload)
        requested: 是否请求投递
    """

    mode: DeliveryMode = DeliveryMode.NONE
    channel: str | None = None
    to: str | None = None
    account_id: str | None = None
    source: str = "delivery"
    requested: bool = False


@dataclass
class FailureDeliveryPlan:
    """失败告警投递计划。

    Attributes:
        mode: 投递模式 (announce 或 webhook)
        channel: 目标渠道
        to: 目标地址
        account_id: 账户 ID
    """

    mode: DeliveryMode = DeliveryMode.ANNOUNCE
    channel: str | None = None
    to: str | None = None
    account_id: str | None = None


def normalize_channel(value: str | None) -> str | None:
    """规范化渠道值。

    Args:
        value: 原始渠道值

    Returns:
        规范化后的渠道值
    """
    if not value or not isinstance(value, str):
        return None
    trimmed = value.strip().lower()
    return trimmed if trimmed else None


def normalize_to(value: str | None) -> str | None:
    """规范化目标地址。

    Args:
        value: 原始目标地址

    Returns:
        规范化后的目标地址
    """
    if not value or not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def normalize_account_id(value: str | None) -> str | None:
    """规范化账户 ID。

    Args:
        value: 原始账户 ID

    Returns:
        规范化后的账户 ID
    """
    if not value or not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def resolve_delivery_plan(
    delivery: Delivery | dict[str, Any] | None,
    payload_channel: str | None = None,
    payload_to: str | None = None,
    payload_deliver: bool | None = None,
) -> DeliveryPlan:
    """解析投递计划。

    根据投递配置和 payload 配置，解析出最终的投递计划。

    Args:
        delivery: 投递配置
        payload_channel: payload 中的渠道配置
        payload_to: payload 中的目标地址
        payload_deliver: payload 中的投递标志

    Returns:
        解析后的投递计划
    """
    if isinstance(delivery, dict):
        delivery = Delivery(
            mode=DeliveryMode(delivery.get("mode", "none")),
            channel=delivery.get("channel"),
            to=delivery.get("to"),
            account_id=delivery.get("account_id"),
            best_effort=delivery.get("best_effort", False),
        )

    has_delivery = delivery is not None

    delivery_channel = normalize_channel(delivery.channel if delivery else None)
    delivery_to = normalize_to(delivery.to if delivery else None)
    delivery_account_id = normalize_account_id(delivery.account_id if delivery else None)

    p_channel = normalize_channel(payload_channel)
    p_to = normalize_to(payload_to)

    channel = delivery_channel or p_channel or "last"
    to = delivery_to or p_to

    if has_delivery and delivery:
        resolved_mode = delivery.mode if delivery.mode != DeliveryMode.NONE else DeliveryMode.ANNOUNCE
        return DeliveryPlan(
            mode=resolved_mode,
            channel=channel if resolved_mode == DeliveryMode.ANNOUNCE else None,
            to=to,
            account_id=delivery_account_id,
            source="delivery",
            requested=resolved_mode == DeliveryMode.ANNOUNCE,
        )

    legacy_mode = (
        "explicit" if payload_deliver is True
        else "off" if payload_deliver is False
        else "auto"
    )
    has_explicit_target = bool(to)
    requested = legacy_mode == "explicit" or (legacy_mode == "auto" and has_explicit_target)

    return DeliveryPlan(
        mode=DeliveryMode.ANNOUNCE if requested else DeliveryMode.NONE,
        channel=channel,
        to=to,
        source="payload",
        requested=requested,
    )


def resolve_failure_destination(
    delivery: Delivery | None,
    global_config: FailureDestination | dict[str, Any] | None = None,
) -> FailureDeliveryPlan | None:
    """解析失败告警目标。

    Args:
        delivery: 投递配置
        global_config: 全局失败告警配置

    Returns:
        失败告警投递计划，如果无需告警则返回 None
    """
    job_failure_dest = delivery.failure_destination if delivery else None

    channel: str | None = None
    to: str | None = None
    account_id: str | None = None
    mode: DeliveryMode = DeliveryMode.ANNOUNCE

    if global_config:
        if isinstance(global_config, dict):
            global_config = FailureDestination(
                channel=global_config.get("channel"),
                to=global_config.get("to"),
                account_id=global_config.get("account_id"),
                mode=DeliveryMode(global_config.get("mode", "announce")),
            )
        channel = normalize_channel(global_config.channel)
        to = normalize_to(global_config.to)
        account_id = normalize_account_id(global_config.account_id)
        mode = global_config.mode

    if job_failure_dest:
        job_channel = normalize_channel(job_failure_dest.channel)
        job_to = normalize_to(job_failure_dest.to)
        job_account_id = normalize_account_id(job_failure_dest.account_id)
        job_mode = job_failure_dest.mode

        if job_channel is not None:
            channel = job_channel
        if job_to is not None:
            to = job_to
        if job_account_id is not None:
            account_id = job_account_id
        if job_mode != DeliveryMode.NONE:
            mode = job_mode

    if not channel and not to and not account_id:
        return None

    if mode == DeliveryMode.WEBHOOK and not to:
        return None

    result = FailureDeliveryPlan(
        mode=mode,
        channel=channel if mode == DeliveryMode.ANNOUNCE else None,
        to=to,
        account_id=account_id,
    )

    if delivery and is_same_delivery_target(delivery, result):
        return None

    return result


def is_same_delivery_target(
    delivery: Delivery,
    failure_plan: FailureDeliveryPlan,
) -> bool:
    """检查失败目标是否与主投递目标相同。

    Args:
        delivery: 主投递配置
        failure_plan: 失败告警计划

    Returns:
        是否相同
    """
    primary_mode = delivery.mode
    if primary_mode == DeliveryMode.NONE:
        return False

    if failure_plan.mode == DeliveryMode.WEBHOOK:
        return primary_mode == DeliveryMode.WEBHOOK and delivery.to == failure_plan.to

    primary_channel_normalized = delivery.channel or "last"
    failure_channel_normalized = failure_plan.channel or "last"

    return (
        failure_channel_normalized == primary_channel_normalized
        and failure_plan.to == delivery.to
        and failure_plan.account_id == delivery.account_id
    )


class DeliveryService:
    """投递服务。

    提供消息投递功能，支持 announce 和 webhook 两种模式。
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        """初始化投递服务。

        Args:
            http_client: HTTP 客户端 (可选，不提供则自动创建)
            timeout: 请求超时时间 (秒)
        """
        self._http_client = http_client
        self._timeout = timeout
        self._owned_client = http_client is None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端。"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        return self._http_client

    async def close(self) -> None:
        """关闭资源。"""
        if self._owned_client and self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def deliver_announce(
        self,
        channel: str,
        to: str,
        message: str,
        account_id: str | None = None,
        thread_id: str | int | None = None,
        best_effort: bool = False,
        send_func: Any = None,
    ) -> DeliveryResult:
        """投递消息到消息渠道。

        Args:
            channel: 目标渠道
            to: 目标地址
            message: 消息内容
            account_id: 账户 ID
            thread_id: 线程 ID
            best_effort: 是否最佳努力投递
            send_func: 发送函数 (由外部注入)

        Returns:
            投递结果
        """
        try:
            if send_func is None:
                logger.warning(
                    "deliver_announce: 未提供发送函数，无法投递",
                    channel=channel,
                    to=to,
                )
                return DeliveryResult(
                    success=False,
                    mode=DeliveryMode.ANNOUNCE,
                    channel=channel,
                    to=to,
                    error="未提供发送函数",
                )

            delivery_context = DeliveryContext(
                channel=channel if channel != "last" else None,
                to=to,
                account_id=account_id,
                thread_id=thread_id,
            )

            result = await send_func(
                to=to,
                text=message,
                channel=channel,
                account_id=account_id,
                thread_id=thread_id,
                delivery_context=delivery_context,
            )

            logger.info(
                "cron 消息投递成功",
                channel=channel,
                to=to,
                account_id=account_id,
            )

            return DeliveryResult(
                success=True,
                mode=DeliveryMode.ANNOUNCE,
                channel=channel,
                to=to,
                message_id=result.message_id if result else None,
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "cron 消息投递失败",
                channel=channel,
                to=to,
                error=error_msg,
            )

            if best_effort:
                logger.info("最佳努力模式: 忽略投递错误")

            return DeliveryResult(
                success=False,
                mode=DeliveryMode.ANNOUNCE,
                channel=channel,
                to=to,
                error=error_msg,
            )

    async def deliver_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        best_effort: bool = False,
    ) -> DeliveryResult:
        """通过 HTTP POST 投递消息。

        Args:
            url: 目标 URL
            payload: 投递内容
            headers: 自定义请求头
            best_effort: 是否最佳努力投递

        Returns:
            投递结果
        """
        try:
            client = await self._get_client()

            default_headers = {
                "Content-Type": "application/json",
                "User-Agent": "TigerClaw-Cron/1.0",
            }
            if headers:
                default_headers.update(headers)

            response = await client.post(
                url,
                json=payload,
                headers=default_headers,
            )

            if response.status_code >= 200 and response.status_code < 300:
                logger.info(
                    "cron webhook 投递成功",
                    url=url,
                    status_code=response.status_code,
                )
                return DeliveryResult(
                    success=True,
                    mode=DeliveryMode.WEBHOOK,
                    to=url,
                    status_code=response.status_code,
                )

            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            logger.warning(
                "cron webhook 投递失败",
                url=url,
                status_code=response.status_code,
            )

            if best_effort:
                logger.info("最佳努力模式: 忽略 webhook 投递错误")

            return DeliveryResult(
                success=False,
                mode=DeliveryMode.WEBHOOK,
                to=url,
                status_code=response.status_code,
                error=error_msg,
            )

        except TimeoutError:
            error_msg = "请求超时"
            logger.error("cron webhook 投递超时", url=url)

            if best_effort:
                logger.info("最佳努力模式: 忽略超时错误")

            return DeliveryResult(
                success=False,
                mode=DeliveryMode.WEBHOOK,
                to=url,
                error=error_msg,
            )

        except Exception as e:
            error_msg = str(e)
            logger.error("cron webhook 投递异常", url=url, error=error_msg)

            if best_effort:
                logger.info("最佳努力模式: 忽略投递异常")

            return DeliveryResult(
                success=False,
                mode=DeliveryMode.WEBHOOK,
                to=url,
                error=error_msg,
            )

    async def deliver_failure_alert(
        self,
        plan: FailureDeliveryPlan,
        job_id: str,
        job_name: str,
        error_message: str,
        send_func: Any = None,
    ) -> DeliveryResult | None:
        """投递失败告警。

        Args:
            plan: 失败告警投递计划
            job_id: 任务 ID
            job_name: 任务名称
            error_message: 错误信息
            send_func: 发送函数 (announce 模式需要)

        Returns:
            投递结果，如果无需投递则返回 None
        """
        if plan.mode == DeliveryMode.NONE:
            return None

        alert_message = self._format_failure_alert(job_id, job_name, error_message)

        if plan.mode == DeliveryMode.WEBHOOK:
            if not plan.to:
                logger.warning("webhook 失败告警缺少 URL")
                return None

            payload = {
                "job_id": job_id,
                "job_name": job_name,
                "error": error_message,
                "timestamp": asyncio.get_event_loop().time(),
            }

            return await self.deliver_webhook(
                url=plan.to,
                payload=payload,
                best_effort=True,
            )

        channel = plan.channel or "last"
        if not plan.to:
            logger.warning("announce 失败告警缺少目标地址")
            return None

        return await self.deliver_announce(
            channel=channel,
            to=plan.to,
            message=alert_message,
            account_id=plan.account_id,
            best_effort=True,
            send_func=send_func,
        )

    def _format_failure_alert(
        self,
        job_id: str,
        job_name: str,
        error_message: str,
    ) -> str:
        """格式化失败告警消息。

        Args:
            job_id: 任务 ID
            job_name: 任务名称
            error_message: 错误信息

        Returns:
            格式化后的告警消息
        """
        max_error_len = 500
        truncated_error = error_message[:max_error_len]
        if len(error_message) > max_error_len:
            truncated_error += "..."

        return (
            f"⚠️ **Cron 任务执行失败**\n\n"
            f"**任务**: {job_name}\n"
            f"**ID**: `{job_id}`\n"
            f"**错误**: {truncated_error}"
        )


_default_delivery_service: DeliveryService | None = None


def get_delivery_service() -> DeliveryService:
    """获取默认投递服务实例。"""
    global _default_delivery_service
    if _default_delivery_service is None:
        _default_delivery_service = DeliveryService()
    return _default_delivery_service
