"""媒体发送辅助函数。

提供媒体文件发送的通用逻辑，包括带头部标题的媒体发送、
附件链接格式化等功能。
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from loguru import logger


async def send_media_with_leading_caption(
    media_urls: list[str],
    caption: str,
    send_fn: Callable[..., Coroutine[Any, Any, Any]],
    on_error: Callable[[Exception, str], Any] | None = None,
) -> bool:
    """发送媒体文件，第一个媒体附带标题，其余不带。

    遍历媒体 URL 列表，第一个 URL 会附带 caption 文本，
    后续的 URL 仅发送媒体本身。发生错误时，如果提供了
    on_error 回调则继续发送其余媒体，否则抛出异常。

    Args:
        media_urls: 媒体 URL 列表。
        caption: 第一条媒体的标题文本。
        send_fn: 发送函数，接收 (media_url, caption) 参数。
        on_error: 错误回调，接收 (exception, media_url) 参数。

    Returns:
        全部发送成功返回 True。

    Raises:
        Exception: 发送失败且未提供 on_error 回调时抛出。
    """
    for i, url in enumerate(media_urls):
        try:
            current_caption = caption if i == 0 else None
            await send_fn(url, current_caption)
        except Exception as e:
            logger.error(f"媒体发送失败: {url}, 错误: {e}")
            if on_error is not None:
                on_error(e, url)
            else:
                raise

    return True


def format_text_with_attachment_links(text: str, media_urls: list[str]) -> str:
    """将媒体 URL 以编号链接形式追加到文本末尾。

    格式示例：
    ```
    原始文本

    附件:
    1. https://example.com/file1.pdf
    2. https://example.com/file2.png
    ```

    Args:
        text: 原始文本。
        media_urls: 媒体 URL 列表。

    Returns:
        格式化后的文本。
    """
    if not media_urls:
        return text

    lines = [text] if text.strip() else []
    lines.append("")
    lines.append("附件:")

    for i, url in enumerate(media_urls, 1):
        lines.append(f"{i}. {url}")

    return "\n".join(lines)
