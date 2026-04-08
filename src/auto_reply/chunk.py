"""文本分块工具。

提供多种分块策略，将长文本拆分为平台限制内的片段：
- 按长度分块（chunkText）：基于字符数限制，括号感知断行
- 按段落分块（chunkByParagraph）：在空行处断开，避免破坏代码块
- Markdown 感知分块（chunkMarkdownText）：正确处理围栏代码块
"""

import re
from collections.abc import Callable
from typing import Literal

ChunkMode = Literal["length", "newline"]

_DEFAULT_CHUNK_LIMIT = 4000
_DEFAULT_CHUNK_MODE: ChunkMode = "length"


class _FenceSpan:
    __slots__ = ("start", "end", "open_line", "marker", "indent")

    def __init__(
        self, start: int, end: int, open_line: str, marker: str, indent: str
    ) -> None:
        self.start = start
        self.end = end
        self.open_line = open_line
        self.marker = marker
        self.indent = indent


def parseFenceSpans(text: str) -> list[tuple[int, int]]:
    """解析围栏代码块的行范围。

    扫描文本中的所有 ```...``` 围栏代码块，
    返回每个代码块的 (起始行索引, 结束行索引) 对。

    Args:
        text: 待解析的文本。

    Returns:
        围栏代码块的 (start, end) 行索引对列表。
    """
    lines = text.split("\n")
    spans: list[tuple[int, int]] = []
    open_info: tuple[int, str, int] | None = None

    for i, line in enumerate(lines):
        match = re.match(r"^( {0,3})(`{3,}|~{3,})(.*)$", line)
        if match:
            marker = match.group(2)
            marker_char = marker[0]
            marker_len = len(marker)
            if open_info is None:
                open_info = (i, marker_char, marker_len)
            elif marker_char == open_info[1] and marker_len >= open_info[2]:
                spans.append((open_info[0], i))
                open_info = None

    if open_info is not None:
        spans.append((open_info[0], len(lines) - 1))

    return spans


def _parse_fence_span_objects(text: str) -> list[_FenceSpan]:
    """解析围栏代码块为完整对象（含字符偏移量）。"""
    spans: list[_FenceSpan] = []
    open_state: tuple[int, str, int, str, str, str] | None = None

    offset = 0
    while offset <= len(text):
        next_newline = text.find("\n", offset)
        line_end = next_newline if next_newline != -1 else len(text)
        line = text[offset:line_end]

        match = re.match(r"^( {0,3})(`{3,}|~{3,})(.*)$", line)
        if match:
            indent = match.group(1)
            marker = match.group(2)
            marker_char = marker[0]
            marker_len = len(marker)
            if open_state is None:
                open_state = (offset, marker_char, marker_len, line, marker, indent)
            elif marker_char == open_state[1] and marker_len >= open_state[2]:
                spans.append(
                    _FenceSpan(
                        start=open_state[0],
                        end=line_end,
                        open_line=open_state[3],
                        marker=open_state[4],
                        indent=open_state[5],
                    )
                )
                open_state = None

        if next_newline == -1:
            break
        offset = next_newline + 1

    if open_state is not None:
        spans.append(
            _FenceSpan(
                start=open_state[0],
                end=len(text),
                open_line=open_state[3],
                marker=open_state[4],
                indent=open_state[5],
            )
        )

    return spans


def _find_fence_span_at(
    spans: list[_FenceSpan], index: int
) -> _FenceSpan | None:
    """二分查找给定字符索引所在的围栏代码块。"""
    low = 0
    high = len(spans) - 1
    while low <= high:
        mid = (low + high) // 2
        span = spans[mid]
        if index <= span.start:
            high = mid - 1
        elif index >= span.end:
            low = mid + 1
        else:
            return span
    return None


def _is_safe_fence_break(spans: list[_FenceSpan], index: int) -> bool:
    """检查给定索引是否不在围栏代码块内部。"""
    return _find_fence_span_at(spans, index) is None


def _scan_paren_aware_breakpoints(
    text: str,
    start: int,
    end: int,
    is_allowed: Callable | None = None,
) -> tuple[int, int]:
    """扫描括号感知的断行点。

    在括号深度为 0 时记录换行符和空白字符位置。

    Returns:
        (last_newline, last_whitespace) 字符索引元组。
    """
    if is_allowed is None:

        def is_allowed(_i: int) -> bool:
            return True

    last_newline = -1
    last_whitespace = -1
    depth = 0

    for i in range(start, end):
        if not is_allowed(i):
            continue
        char = text[i]
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        elif depth == 0:
            if char == "\n":
                last_newline = i
            elif char in (" ", "\t", "\r"):
                last_whitespace = i

    return last_newline, last_whitespace


def chunkText(text: str, limit: int) -> list[str]:
    """按长度分块文本。

    在限制范围内优先在换行符处断开，其次在空白处断开。
    支持括号感知：不会在括号内部断行。

    Args:
        text: 待分块文本。
        limit: 每块最大字符数。

    Returns:
        分块后的文本列表。
    """
    if not text:
        return []
    if limit <= 0 or len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while len(remaining) > limit:
        window = remaining[:limit]
        last_newline, last_whitespace = _scan_paren_aware_breakpoints(window, 0, len(window))
        break_idx = last_newline if last_newline > 0 else (last_whitespace if last_whitespace > 0 else limit)

        raw_chunk = remaining[:break_idx]
        chunk = raw_chunk.rstrip()
        if chunk:
            chunks.append(chunk)

        broke_on_sep = break_idx < len(remaining) and remaining[break_idx].isspace()
        next_start = min(len(remaining), break_idx + (1 if broke_on_sep else 0))
        remaining = remaining[next_start:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def chunkByParagraph(
    text: str, limit: int, split_long: bool = True
) -> list[str]:
    """按段落分块文本。

    在空行（\\n\\s*\\n+）处拆分段落，将短段落合并到一个块中。
    如果单个段落超过限制，回退到 chunkText 进行长度分块。
    会检查围栏代码块范围，避免在代码块内部断开。

    Args:
        text: 待分块文本。
        limit: 每块最大字符数。
        split_long: 超长段落是否拆分。

    Returns:
        分块后的文本列表。
    """
    if not text:
        return []
    if limit <= 0:
        return [text]

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    paragraph_re = re.compile(r"\n[\t ]*\n+")
    if not paragraph_re.search(normalized):
        if len(normalized) <= limit:
            return [normalized]
        if not split_long:
            return [normalized]
        return chunkText(normalized, limit)

    fence_spans = _parse_fence_span_objects(normalized)

    parts: list[str] = []
    re_global = re.compile(r"\n[\t ]*\n+")
    last_index = 0
    for match in re_global.finditer(normalized):
        idx = match.start()
        if not _is_safe_fence_break(fence_spans, idx):
            continue
        parts.append(normalized[last_index:idx])
        last_index = match.end()
    parts.append(normalized[last_index:])

    chunks: list[str] = []
    for part in parts:
        paragraph = re.sub(r"\s+$", "", part)
        if not paragraph.strip():
            continue
        if len(paragraph) <= limit:
            chunks.append(paragraph)
        elif split_long:
            chunks.extend(chunkText(paragraph, limit))
        else:
            chunks.append(paragraph)

    return chunks


def chunkMarkdownText(text: str, limit: int) -> list[str]:
    """Markdown 感知的文本分块。

    类似 chunkText，但感知围栏代码块边界。
    若必须在代码块内部断开，会关闭围栏（追加 ```）
    并在下一块重新打开（追加 ```lang）。

    Args:
        text: 待分块的 Markdown 文本。
        limit: 每块最大字符数。

    Returns:
        分块后的文本列表。
    """
    if not text:
        return []
    if limit <= 0 or len(text) <= limit:
        return [text]

    chunks: list[str] = []
    spans = _parse_fence_span_objects(text)
    start = 0
    reopen_fence: _FenceSpan | None = None

    while start < len(text):
        reopen_prefix = f"{reopen_fence.open_line}\n" if reopen_fence else ""
        content_limit = max(1, limit - len(reopen_prefix))

        if len(text) - start <= content_limit:
            final_chunk = f"{reopen_prefix}{text[start:]}"
            if final_chunk:
                chunks.append(final_chunk)
            break

        window_end = min(len(text), start + content_limit)
        soft_break = _pick_safe_break_index(text, start, window_end, spans)
        break_idx = soft_break if soft_break > start else window_end

        initial_fence = (
            None
            if _is_safe_fence_break(spans, break_idx)
            else _find_fence_span_at(spans, break_idx)
        )

        fence_to_split = initial_fence
        if initial_fence:
            close_line = f"{initial_fence.indent}{initial_fence.marker}"
            max_idx_if_need_newline = start + (content_limit - (len(close_line) + 1))

            if max_idx_if_need_newline <= start:
                fence_to_split = None
                break_idx = window_end
            else:
                min_progress_idx = min(
                    len(text),
                    max(start + 1, initial_fence.start + len(initial_fence.open_line) + 2),
                )
                max_idx_if_already_newline = start + (content_limit - len(close_line))

                picked_newline = False
                last_newline_pos = text.rfind(
                    "\n", start, max(start, max_idx_if_already_newline - 1) + 1
                )
                while last_newline_pos >= start:
                    candidate_break = last_newline_pos + 1
                    if candidate_break < min_progress_idx:
                        break
                    candidate_fence = _find_fence_span_at(spans, candidate_break)
                    if candidate_fence and candidate_fence.start == initial_fence.start:
                        break_idx = candidate_break
                        picked_newline = True
                        break
                    last_newline_pos = text.rfind("\n", start, last_newline_pos)

                if not picked_newline:
                    if min_progress_idx > max_idx_if_already_newline:
                        fence_to_split = None
                        break_idx = window_end
                    else:
                        break_idx = max(min_progress_idx, max_idx_if_need_newline)

                fence_at_break = _find_fence_span_at(spans, break_idx)
                fence_to_split = (
                    fence_at_break
                    if fence_at_break and fence_at_break.start == initial_fence.start
                    else None
                )

        raw_content = text[start:break_idx]
        if not raw_content:
            break

        raw_chunk = f"{reopen_prefix}{raw_content}"
        broke_on_sep = break_idx < len(text) and text[break_idx].isspace()
        next_start = min(len(text), break_idx + (1 if broke_on_sep else 0))

        if fence_to_split:
            close_line = f"{fence_to_split.indent}{fence_to_split.marker}"
            if raw_chunk.endswith("\n"):
                raw_chunk = f"{raw_chunk}{close_line}"
            else:
                raw_chunk = f"{raw_chunk}\n{close_line}"
            reopen_fence = fence_to_split
        else:
            next_start = _skip_leading_newlines(text, next_start)
            reopen_fence = None

        chunks.append(raw_chunk)
        start = next_start

    return chunks


def _skip_leading_newlines(value: str, start: int = 0) -> int:
    """跳过前导换行符。"""
    i = start
    while i < len(value) and value[i] == "\n":
        i += 1
    return i


def _pick_safe_break_index(
    text: str,
    start: int,
    end: int,
    spans: list[_FenceSpan],
) -> int:
    """在安全范围内选择最佳断行索引。"""
    last_newline, last_whitespace = _scan_paren_aware_breakpoints(
        text, start, end, lambda index: _is_safe_fence_break(spans, index)
    )
    if last_newline > start:
        return last_newline
    if last_whitespace > start:
        return last_whitespace
    return -1


def chunkTextWithMode(text: str, limit: int, mode: ChunkMode) -> list[str]:
    """根据模式选择分块策略。

    Args:
        text: 待分块文本。
        limit: 每块最大字符数。
        mode: 分块模式（"length" 或 "newline"）。

    Returns:
        分块后的文本列表。
    """
    if mode == "newline":
        return chunkByParagraph(text, limit)
    return chunkText(text, limit)


def chunkMarkdownTextWithMode(text: str, limit: int, mode: ChunkMode) -> list[str]:
    """根据模式选择 Markdown 感知分块策略。

    Args:
        text: 待分块的 Markdown 文本。
        limit: 每块最大字符数。
        mode: 分块模式（"length" 或 "newline"）。

    Returns:
        分块后的文本列表。
    """
    if mode == "newline":
        paragraph_chunks = chunkByParagraph(text, limit, split_long=False)
        out: list[str] = []
        for chunk in paragraph_chunks:
            nested = chunkMarkdownText(chunk, limit)
            if not nested and chunk:
                out.append(chunk)
            else:
                out.extend(nested)
        return out
    return chunkMarkdownText(text, limit)


def resolveTextChunkLimit(
    cfg: dict | None = None,
    provider: str | None = None,
    account_id: str | None = None,
) -> int:
    """解析文本分块大小限制。

    从配置中按优先级查找：
    1. cfg["channels"][provider]["accounts"][account_id]["textChunkLimit"]
    2. cfg["channels"][provider]["textChunkLimit"]

    Args:
        cfg: 配置字典。
        provider: 渠道提供商标识。
        account_id: 账户 ID。

    Returns:
        分块大小限制，默认 4000。
    """
    if cfg and provider:
        channels_config = cfg.get("channels")
        if isinstance(channels_config, dict):
            provider_config = channels_config.get(provider)
            if isinstance(provider_config, dict):
                accounts = provider_config.get("accounts")
                if isinstance(accounts, dict) and account_id:
                    account_entry = accounts.get(account_id)
                    if isinstance(account_entry, dict):
                        limit = account_entry.get("textChunkLimit")
                        if isinstance(limit, int) and limit > 0:
                            return limit
                limit = provider_config.get("textChunkLimit")
                if isinstance(limit, int) and limit > 0:
                    return limit
    return _DEFAULT_CHUNK_LIMIT


def resolveChunkMode(
    cfg: dict | None = None,
    provider: str | None = None,
    account_id: str | None = None,
) -> ChunkMode:
    """解析分块模式。

    从配置中按优先级查找：
    1. cfg["channels"][provider]["accounts"][account_id]["chunkMode"]
    2. cfg["channels"][provider]["chunkMode"]

    Args:
        cfg: 配置字典。
        provider: 渠道提供商标识。
        account_id: 账户 ID。

    Returns:
        分块模式，默认 "length"。
    """
    if cfg and provider:
        channels_config = cfg.get("channels")
        if isinstance(channels_config, dict):
            provider_config = channels_config.get(provider)
            if isinstance(provider_config, dict):
                accounts = provider_config.get("accounts")
                if isinstance(accounts, dict) and account_id:
                    account_entry = accounts.get(account_id)
                    if isinstance(account_entry, dict):
                        mode = account_entry.get("chunkMode")
                        if mode in ("length", "newline"):
                            return mode
                mode = provider_config.get("chunkMode")
                if mode in ("length", "newline"):
                    return mode
    return _DEFAULT_CHUNK_MODE
