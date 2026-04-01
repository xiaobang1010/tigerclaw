"""Frontmatter 解析模块。

参考 OpenClaw 的 markdown/frontmatter.ts 实现。
支持 YAML 和行式 frontmatter 解析。
"""

import re
from typing import Any

import yaml

from services.skills.types import ParsedSkillFrontmatter


def extract_frontmatter_block(content: str) -> str | None:
    """提取 frontmatter 块。

    Args:
        content: 文件内容。

    Returns:
        frontmatter 块文本，如果没有则返回 None。
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---"):
        return None
    end_index = normalized.find("\n---", 3)
    if end_index == -1:
        return None
    return normalized[4:end_index]


def _strip_quotes(value: str) -> str:
    """移除字符串两端的引号。

    Args:
        value: 原始字符串。

    Returns:
        移除引号后的字符串。
    """
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _coerce_yaml_value(value: Any) -> tuple[str, str] | None:
    """将 YAML 值转换为字符串。

    Args:
        value: YAML 解析的值。

    Returns:
        (字符串值, 类型) 元组或 None。
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip(), "scalar"
    if isinstance(value, bool | int | float):
        return str(value), "scalar"
    if isinstance(value, dict | list):
        try:
            import json

            return json.dumps(value), "structured"
        except (TypeError, ValueError):
            return None
    return None


def _parse_yaml_frontmatter(block: str) -> dict[str, tuple[str, str]] | None:
    """解析 YAML frontmatter 块。

    Args:
        block: frontmatter 块文本。

    Returns:
        解析后的键值对字典，键为字符串，值为 (值, 类型) 元组。
    """
    try:
        parsed = yaml.safe_load(block)
        if not parsed or not isinstance(parsed, dict):
            return None
        result: dict[str, tuple[str, str]] = {}
        for raw_key, value in parsed.items():
            key = str(raw_key).strip()
            if not key:
                continue
            coerced = _coerce_yaml_value(value)
            if coerced:
                result[key] = coerced
        return result
    except yaml.YAMLError:
        return None


def _extract_multiline_value(lines: list[str], start_index: int) -> tuple[str, int]:
    """提取多行值。

    Args:
        lines: 行列表。
        start_index: 起始索引。

    Returns:
        (值, 消耗的行数) 元组。
    """
    value_lines: list[str] = []
    i = start_index + 1
    while i < len(lines):
        line = lines[i]
        if line and not line.startswith(" ") and not line.startswith("\t"):
            break
        value_lines.append(line)
        i += 1
    combined = "\n".join(value_lines).strip()
    return combined, i - start_index


def _parse_line_frontmatter(block: str) -> dict[str, tuple[str, str, str]]:
    """解析行式 frontmatter。

    Args:
        block: frontmatter 块文本。

    Returns:
        解析后的字典，值为 (值, 类型, 原始行内值) 元组。
    """
    result: dict[str, tuple[str, str, str]] = {}
    lines = block.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r"^([\w-]+):\s*(.*)$", line)
        if not match:
            i += 1
            continue
        key = match.group(1)
        inline_value = match.group(2).strip()
        if not key:
            i += 1
            continue
        if not inline_value and i + 1 < len(lines):
            next_line = lines[i + 1]
            if next_line.startswith(" ") or next_line.startswith("\t"):
                value, lines_consumed = _extract_multiline_value(lines, i)
                if value:
                    result[key] = (value, "multiline", inline_value)
                i += lines_consumed
                continue
        value = _strip_quotes(inline_value)
        if value:
            result[key] = (value, "inline", inline_value)
        i += 1
    return result


def _is_yaml_block_scalar_indicator(value: str) -> bool:
    """检查是否为 YAML 块标量指示符。

    Args:
        value: 要检查的值。

    Returns:
        是否为块标量指示符。
    """
    return bool(re.match(r"^[|>][+-]?(\d+)?[+-]?$", value))


def _should_prefer_inline_line_value(
    line_entry: tuple[str, str, str],
    yaml_value: tuple[str, str],
) -> bool:
    """判断是否应优先使用行内值。

    Args:
        line_entry: 行解析结果 (值, 类型, 原始值)。
        yaml_value: YAML 解析结果 (值, 类型)。

    Returns:
        是否优先使用行内值。
    """
    _, yaml_kind = yaml_value
    _, line_kind, raw_inline = line_entry
    if yaml_kind != "structured":
        return False
    if line_kind != "inline":
        return False
    if _is_yaml_block_scalar_indicator(raw_inline):
        return False
    return ":" in line_entry[0]


def parse_frontmatter(content: str) -> ParsedSkillFrontmatter:
    """解析 frontmatter。

    支持 YAML 和行式 frontmatter，优先使用 YAML 解析，
    对于特殊情况会回退到行式解析。

    Args:
        content: 文件内容或 frontmatter 块。

    Returns:
        解析后的键值对字典。
    """
    block = extract_frontmatter_block(content)
    if not block:
        if ":" in content and "\n" not in content:
            result: ParsedSkillFrontmatter = {}
            for line in content.split(","):
                if ":" in line:
                    key, _, value = line.partition(":")
                    result[key.strip()] = value.strip().strip('"').strip("'")
            return result
        return {}
    line_parsed = _parse_line_frontmatter(block)
    yaml_parsed = _parse_yaml_frontmatter(block)
    if yaml_parsed is None:
        return {k: v[0] for k, v in line_parsed.items()}
    merged: ParsedSkillFrontmatter = {}
    for key, yaml_value in yaml_parsed.items():
        merged[key] = yaml_value[0]
        line_entry = line_parsed.get(key)
        if line_entry and _should_prefer_inline_line_value(line_entry, yaml_value):
            merged[key] = line_entry[0]
    for key, line_entry in line_parsed.items():
        if key not in merged:
            merged[key] = line_entry[0]
    return merged


def extract_content(content: str) -> str:
    """提取正文内容（移除 frontmatter）。

    Args:
        content: 文件完整内容。

    Returns:
        正文内容。
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---"):
        return content.strip()
    end_index = normalized.find("\n---", 3)
    if end_index == -1:
        return content.strip()
    body = normalized[end_index + 5 :]
    return body.strip()


def parse_skill_file(content: str) -> tuple[ParsedSkillFrontmatter, str]:
    """解析 Skill 文件，返回 frontmatter 和正文。

    Args:
        content: 文件完整内容。

    Returns:
        (frontmatter, body) 元组。
    """
    frontmatter = parse_frontmatter(content)
    body = extract_content(content)
    return frontmatter, body
