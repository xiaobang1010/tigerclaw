"""OpenAI 图像内容处理模块。

处理 OpenAI Chat Completions API 中的 image_url 内容类型，
支持 URL 获取、base64 解析、data URI 解析等功能。
"""

import base64
import re
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

DEFAULT_IMAGE_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_IMAGE_MIMES: set[str] = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "image/heif",
}
DEFAULT_MAX_IMAGE_PARTS = 8
DEFAULT_MAX_TOTAL_IMAGE_BYTES = 20 * 1024 * 1024
DEFAULT_IMAGE_TIMEOUT_MS = 30000
DEFAULT_IMAGE_MAX_REDIRECTS = 3


@dataclass
class ImageLimits:
    """图像处理限制配置。"""

    max_bytes: int = DEFAULT_IMAGE_MAX_BYTES
    allowed_mimes: set[str] = field(default_factory=lambda: DEFAULT_IMAGE_MIMES.copy())
    allow_url: bool = False
    timeout_ms: int = DEFAULT_IMAGE_TIMEOUT_MS
    max_redirects: int = DEFAULT_IMAGE_MAX_REDIRECTS
    url_allowlist: list[str] | None = None


@dataclass
class ImageSource:
    """图像源。

    type 为 "base64" 时，data 为 base64 编码的图像数据。
    type 为 "url" 时，url 为图像的 URL 地址。
    """

    type: Literal["base64", "url"]
    data: str | None = None
    url: str | None = None
    media_type: str | None = None


@dataclass
class ResolvedImageContent:
    """解析后的图像内容。"""

    data: str
    mime_type: str


class ImageProcessingError(Exception):
    """图像处理错误。"""

    pass


def estimate_base64_decoded_bytes(data: str) -> int:
    """估算 base64 解码后的字节数。

    Args:
        data: base64 编码的字符串。

    Returns:
        估算的解码后字节数。
    """
    data = data.strip()
    padding = data.count("=")
    return (len(data) * 3) // 4 - padding


def normalize_mime_type(mime: str | None) -> str | None:
    """规范化 MIME 类型。

    Args:
        mime: 原始 MIME 类型字符串。

    Returns:
        规范化后的 MIME 类型，如果无效则返回 None。
    """
    if not mime:
        return None
    parts = mime.split(";")
    normalized = parts[0].strip().lower() if parts else None
    return normalized if normalized else None


def parse_data_uri(uri: str) -> tuple[str | None, str]:
    """解析 data URI 格式。

    Args:
        uri: data URI 字符串，格式为 data:[<mediatype>][;base64],<data>

    Returns:
        元组 (media_type, data)，如果解析失败则返回 (None, "")

    Raises:
        ImageProcessingError: 如果 data URI 格式无效。
    """
    match = re.match(r"^data:([^,]*?),(.*)$", uri, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ImageProcessingError("Invalid data URI format")

    metadata = match.group(1).strip() if match.group(1) else ""
    data = match.group(2) if match.group(2) else ""

    metadata_parts = [p.strip() for p in metadata.split(";") if p.strip()]
    is_base64 = any(p.lower() == "base64" for p in metadata_parts)

    if not is_base64:
        raise ImageProcessingError("image_url data URI must be base64 encoded")

    if not data.strip():
        raise ImageProcessingError("image_url data URI is missing payload data")

    media_type = next((p for p in metadata_parts if "/" in p), None)

    return media_type, data


def parse_image_url(url: str) -> ImageSource:
    """解析 image_url，支持 URL、base64、data URI。

    Args:
        url: 图像 URL 或 data URI。

    Returns:
        ImageSource 对象。

    Raises:
        ImageProcessingError: 如果 URL 格式无效。
    """
    url = url.strip()
    if not url:
        raise ImageProcessingError("Empty image URL")

    if url.lower().startswith("data:"):
        media_type, data = parse_data_uri(url)
        return ImageSource(
            type="base64",
            data=data,
            media_type=media_type,
        )

    if url.lower().startswith(("http://", "https://")):
        return ImageSource(type="url", url=url)

    if re.match(r"^[A-Za-z0-9+/]+=*$", url):
        return ImageSource(type="base64", data=url, media_type=None)

    raise ImageProcessingError(f"Invalid image URL format: {url[:50]}...")


def canonicalize_base64(data: str) -> str | None:
    """规范化 base64 字符串。

    移除空白字符并验证格式。

    Args:
        data: 原始 base64 字符串。

    Returns:
        规范化后的 base64 字符串，如果无效则返回 None。
    """
    data = re.sub(r"\s", "", data)
    if not data:
        return None

    padding_needed = (4 - len(data) % 4) % 4
    data += "=" * padding_needed

    try:
        base64.b64decode(data, validate=True)
        return data
    except Exception:
        return None


def validate_mime_type(mime: str | None, allowed: set[str]) -> str:
    """验证 MIME 类型。

    Args:
        mime: MIME 类型。
        allowed: 允许的 MIME 类型集合。

    Returns:
        验证后的 MIME 类型。

    Raises:
        ImageProcessingError: 如果 MIME 类型不支持。
    """
    normalized = normalize_mime_type(mime)
    if not normalized:
        return "image/png"

    if normalized not in allowed:
        raise ImageProcessingError(f"Unsupported image MIME type: {normalized}")

    return normalized


def detect_mime_from_bytes(data: bytes) -> str | None:
    """从字节流检测 MIME 类型。

    通过文件头魔数检测图像类型。

    Args:
        data: 图像字节数据。

    Returns:
        检测到的 MIME 类型，如果无法识别则返回 None。
    """
    if len(data) < 4:
        return None

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"

    if data[:2] == b"\xff\xd8":
        return "image/jpeg"

    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    if data[:4] in (b"ftyp", b"heic", b"heix", b"hevc", b"hevx"):
        return "image/heic"

    return None


async def fetch_image_from_url(
    url: str,
    limits: ImageLimits,
) -> ResolvedImageContent:
    """从 URL 获取图像。

    Args:
        url: 图像 URL。
        limits: 图像限制配置。

    Returns:
        ResolvedImageContent 对象。

    Raises:
        ImageProcessingError: 如果获取失败或违反限制。
    """
    if not limits.allow_url:
        raise ImageProcessingError("image_url URL sources are disabled by config")

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ImageProcessingError(f"Invalid URL: {url}")

    if limits.url_allowlist:
        hostname = parsed.netloc.lower()
        if not any(hostname == allowed.lower() or hostname.endswith(f".{allowed.lower()}") for allowed in limits.url_allowlist):
            raise ImageProcessingError(f"URL hostname not in allowlist: {hostname}")

    timeout_seconds = limits.timeout_ms / 1000.0

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=True,
        max_redirects=limits.max_redirects,
    ) as client:
        try:
            response = await client.get(
                url,
                headers={"User-Agent": "TigerClaw-Gateway/1.0"},
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            raise ImageProcessingError(f"Timeout fetching image from URL: {url}") from None
        except httpx.HTTPStatusError as e:
            raise ImageProcessingError(f"Failed to fetch image: {e.response.status_code}") from None
        except httpx.HTTPError as e:
            raise ImageProcessingError(f"HTTP error fetching image: {e}") from None

        content_length = response.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > limits.max_bytes:
                    raise ImageProcessingError(
                        f"Image too large: {size} bytes (limit: {limits.max_bytes} bytes)"
                    )
            except ValueError:
                pass

        data = response.content
        if len(data) > limits.max_bytes:
            raise ImageProcessingError(
                f"Image too large: {len(data)} bytes (limit: {limits.max_bytes} bytes)"
            )

        content_type = response.headers.get("content-type")
        declared_mime = normalize_mime_type(content_type)

        detected_mime = detect_mime_from_bytes(data)
        mime_type = detected_mime or declared_mime or "application/octet-stream"

        if declared_mime and declared_mime.startswith("image/") and detected_mime and not detected_mime.startswith("image/"):
            raise ImageProcessingError(f"Unsupported image MIME type: {detected_mime}")

        mime_type = validate_mime_type(mime_type, limits.allowed_mimes)

        base64_data = base64.b64encode(data).decode("utf-8")

        return ResolvedImageContent(data=base64_data, mime_type=mime_type)


def extract_image_urls(content: Any) -> list[str]:
    """从消息内容中提取图像 URL。

    支持以下格式：
    - 字符串内容：返回空列表
    - 数组内容：提取 type="image_url" 的部分

    Args:
        content: 消息内容。

    Returns:
        图像 URL 列表。
    """
    if not isinstance(content, list):
        return []

    urls: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue

        if part.get("type") != "image_url":
            continue

        image_url = part.get("image_url")
        if isinstance(image_url, str):
            url = image_url.strip()
            if url:
                urls.append(url)
        elif isinstance(image_url, dict):
            url = image_url.get("url")
            if isinstance(url, str):
                url = url.strip()
                if url:
                    urls.append(url)

    return urls


async def resolve_image_source(
    source: ImageSource,
    limits: ImageLimits,
) -> ResolvedImageContent:
    """解析单个图像源。

    Args:
        source: 图像源。
        limits: 图像限制配置。

    Returns:
        ResolvedImageContent 对象。

    Raises:
        ImageProcessingError: 如果解析失败或违反限制。
    """
    if source.type == "base64":
        if not source.data:
            raise ImageProcessingError("image_url base64 source has no data")

        estimated_bytes = estimate_base64_decoded_bytes(source.data)
        if estimated_bytes > limits.max_bytes:
            raise ImageProcessingError(
                f"Image too large: {estimated_bytes} bytes (limit: {limits.max_bytes} bytes)"
            )

        canonical_data = canonicalize_base64(source.data)
        if not canonical_data:
            raise ImageProcessingError("image_url base64 source has invalid 'data' field")

        try:
            decoded = base64.b64decode(canonical_data)
        except Exception as e:
            raise ImageProcessingError(f"Failed to decode base64 data: {e}") from None

        if len(decoded) > limits.max_bytes:
            raise ImageProcessingError(
                f"Image too large: {len(decoded)} bytes (limit: {limits.max_bytes} bytes)"
            )

        detected_mime = detect_mime_from_bytes(decoded)
        mime_type = detected_mime or normalize_mime_type(source.media_type) or "image/png"
        mime_type = validate_mime_type(mime_type, limits.allowed_mimes)

        return ResolvedImageContent(data=canonical_data, mime_type=mime_type)

    if source.type == "url":
        if not source.url:
            raise ImageProcessingError("image_url URL source has no URL")
        return await fetch_image_from_url(source.url, limits)

    raise ImageProcessingError(f"Unsupported image source type: {source.type}")


async def resolve_images_for_request(
    urls: list[str],
    limits: ImageLimits,
    max_parts: int = DEFAULT_MAX_IMAGE_PARTS,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_IMAGE_BYTES,
) -> list[ResolvedImageContent]:
    """解析请求中的所有图像。

    Args:
        urls: 图像 URL 列表。
        limits: 图像限制配置。
        max_parts: 最大图像数量。
        max_total_bytes: 最大总字节数。

    Returns:
        解析后的图像内容列表。

    Raises:
        ImageProcessingError: 如果解析失败或违反限制。
    """
    if not urls:
        return []

    if len(urls) > max_parts:
        raise ImageProcessingError(
            f"Too many image_url parts ({len(urls)}; limit {max_parts})"
        )

    images: list[ResolvedImageContent] = []
    total_bytes = 0

    for url in urls:
        source = parse_image_url(url)

        if source.type == "base64" and source.data:
            source_bytes = estimate_base64_decoded_bytes(source.data)
            if total_bytes + source_bytes > max_total_bytes:
                raise ImageProcessingError(
                    f"Total image payload too large ({total_bytes + source_bytes}; limit {max_total_bytes})"
                )

        image = await resolve_image_source(source, limits)

        image_bytes = estimate_base64_decoded_bytes(image.data)
        total_bytes += image_bytes

        if total_bytes > max_total_bytes:
            raise ImageProcessingError(
                f"Total image payload too large ({total_bytes}; limit {max_total_bytes})"
            )

        images.append(image)

    return images


def resolve_active_turn_context(messages: list[Any]) -> dict[str, Any]:
    """解析活跃轮次的上下文。

    从消息列表中找到最后一个用户消息，提取其中的图像 URL。

    Args:
        messages: 消息列表。

    Returns:
        包含 active_turn_index, active_user_message_index, urls 的字典。
    """
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not isinstance(msg, dict):
            continue

        role = msg.get("role", "")
        if isinstance(role, str):
            role = role.strip()
        else:
            continue

        normalized_role = "tool" if role == "function" else role
        if normalized_role not in ("user", "tool"):
            continue

        return {
            "active_turn_index": i,
            "active_user_message_index": i if normalized_role == "user" else -1,
            "urls": extract_image_urls(msg.get("content")) if normalized_role == "user" else [],
        }

    return {
        "active_turn_index": -1,
        "active_user_message_index": -1,
        "urls": [],
    }
