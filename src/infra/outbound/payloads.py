"""载荷归一化处理。

将原始回复载荷转换为归一化的出站格式，处理内嵌指令、
媒体 URL 合并、推理载荷过滤等逻辑。
"""

from __future__ import annotations

import re

from loguru import logger

from infra.outbound.types import NormalizedOutboundPayload


def parse_reply_directives(text: str) -> dict:
    """从文本中提取内嵌指令。

    支持的指令格式：
    - [mediaUrl:...] — 嵌入媒体 URL
    - [replyTo:...] — 指定回复目标
    - [silent] — 静默发送标记

    Args:
        text: 原始文本。

    Returns:
        包含解析后指令和清理文本的字典。
    """
    media_urls: list[str] = []
    reply_to_id: str | None = None
    is_silent = False

    cleaned_lines: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()

        media_url_match = re.match(r"^\[mediaUrl:(.+)\]$", stripped)
        if media_url_match:
            url = media_url_match.group(1).strip()
            if url:
                media_urls.append(url)
            continue

        reply_to_match = re.match(r"^\[replyTo:(.+)\]$", stripped)
        if reply_to_match:
            reply_to_id = reply_to_match.group(1).strip()
            continue

        if stripped == "[silent]":
            is_silent = True
            continue

        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines).strip()

    return {
        "text": cleaned_text,
        "media_urls": media_urls,
        "reply_to_id": reply_to_id,
        "is_silent": is_silent,
    }


def _merge_media_urls(*lists: list[str] | str | None) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []

    for item in lists:
        if item is None:
            continue
        entries = [item] if isinstance(item, str) else item
        for entry in entries:
            trimmed = entry.strip() if isinstance(entry, str) else ""
            if trimmed and trimmed not in seen:
                seen.add(trimmed)
                merged.append(trimmed)

    return merged


def _is_renderable(payload: dict) -> bool:
    """判断载荷是否包含可渲染内容。"""
    text = payload.get("text", "")
    if isinstance(text, str) and text.strip():
        return True

    media_url = payload.get("media_url") or payload.get("mediaUrl")
    if media_url:
        return True

    media_urls = payload.get("media_urls") or payload.get("mediaUrls")
    if media_urls and len(media_urls) > 0:
        return True

    if payload.get("interactive"):
        return True

    return bool(payload.get("channel_data") or payload.get("channelData"))


def normalize_reply_payloads_for_delivery(payloads: list[dict]) -> list[NormalizedOutboundPayload]:
    """将原始回复载荷归一化为出站格式。

    处理流程：
    1. 过滤推理载荷 (is_reasoning=True)
    2. 解析内嵌指令
    3. 合并 mediaUrl/mediaUrls
    4. 跳过无媒体的静默载荷
    5. 跳过不可渲染的载荷

    Args:
        payloads: 原始回复载荷列表。

    Returns:
        归一化的出站载荷列表。
    """
    normalized: list[NormalizedOutboundPayload] = []

    for payload in payloads:
        if payload.get("is_reasoning"):
            continue

        text = payload.get("text", "") or ""
        parsed = parse_reply_directives(text)

        explicit_media_urls = payload.get("mediaUrls") or payload.get("media_urls")
        if isinstance(explicit_media_urls, str):
            explicit_media_urls = [explicit_media_urls]
        directive_media_urls = parsed.get("media_urls", [])

        merged_media: list[str] = []
        seen: set[str] = set()

        for source in [explicit_media_urls, directive_media_urls]:
            if not source:
                continue
            for url in source:
                trimmed = url.strip() if isinstance(url, str) else ""
                if trimmed and trimmed not in seen:
                    seen.add(trimmed)
                    merged_media.append(trimmed)

        explicit_media_url = payload.get("mediaUrl") or payload.get("media_url")
        if explicit_media_url and isinstance(explicit_media_url, str):
            trimmed = explicit_media_url.strip()
            if trimmed and trimmed not in seen:
                merged_media.append(trimmed)

        cleaned_text = parsed.get("text", "")

        if parsed.get("is_silent") and len(merged_media) == 0:
            continue

        result = NormalizedOutboundPayload(
            text=cleaned_text,
            media_urls=merged_media,
            audio_as_voice=bool(payload.get("audio_as_voice") or payload.get("audioAsVoice")),
            interactive=payload.get("interactive"),
            channel_data=payload.get("channel_data") or payload.get("channelData"),
        )

        if not result.text.strip() and not result.media_urls and not result.interactive and not result.channel_data:
            continue

        normalized.append(result)

    logger.debug(f"载荷归一化: {len(payloads)} -> {len(normalized)} 条")
    return normalized
