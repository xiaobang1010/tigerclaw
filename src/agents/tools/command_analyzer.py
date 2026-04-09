"""增强命令分析器。

对 shell 命令进行安全分析，检测危险模式、编码绕过和 shell 结构。
"""

import base64
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NamedTuple

from loguru import logger


class CommandThreatLevel(StrEnum):
    """命令威胁等级。"""

    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"


class _DangerPattern(NamedTuple):
    """危险模式定义。"""

    pattern: str
    threat_level: CommandThreatLevel
    description: str


@dataclass
class CommandAnalysis:
    """命令分析结果。"""

    threat_level: CommandThreatLevel = CommandThreatLevel.SAFE
    patterns_matched: list[str] = field(default_factory=list)
    decoded_commands: list[str] = field(default_factory=list)
    has_encoding: bool = False
    has_shell_escape: bool = False
    has_privilege_escalation: bool = False
    has_network_access: bool = False
    has_file_destruction: bool = False


class CommandAnalyzer:
    """增强命令分析器。

    综合分析 shell 命令的安全威胁，包括危险模式匹配、
    编码绕过检测和 shell 结构分析。
    """

    DANGER_PATTERNS: list[_DangerPattern] = [
        _DangerPattern(r"rm\s+-rf\s+/", CommandThreatLevel.CRITICAL, "递归强制删除根目录"),
        _DangerPattern(r"mkfs", CommandThreatLevel.CRITICAL, "格式化文件系统"),
        _DangerPattern(r"dd\s+if=/dev/zero", CommandThreatLevel.CRITICAL, "磁盘清零"),
        _DangerPattern(r"chmod\s+(-R\s+)?777", CommandThreatLevel.DANGER, "授予全部权限"),
        _DangerPattern(r"chown\s+-R", CommandThreatLevel.DANGER, "递归修改文件所有者"),
        _DangerPattern(r"\bsudo\b", CommandThreatLevel.WARNING, "以超级用户执行"),
        _DangerPattern(r"\bsu\s", CommandThreatLevel.WARNING, "切换用户"),
        _DangerPattern(r"\bnohup\b", CommandThreatLevel.WARNING, "后台持久运行"),
        _DangerPattern(r"\bdisown\b", CommandThreatLevel.WARNING, "脱离终端控制"),
        _DangerPattern(r":\(\)\{.*:\|:&.*\}", CommandThreatLevel.CRITICAL, "fork 炸弹"),
        _DangerPattern(r">\s*/dev/sd", CommandThreatLevel.CRITICAL, "直接写入块设备"),
        _DangerPattern(r"curl\s.*\|\s*(sh|bash)", CommandThreatLevel.CRITICAL, "远程脚本执行(curl)"),
        _DangerPattern(r"wget\s.*\|\s*(sh|bash)", CommandThreatLevel.CRITICAL, "远程脚本执行(wget)"),
        _DangerPattern(r"\bformat(\.com)?\b", CommandThreatLevel.CRITICAL, "Windows 格式化磁盘"),
        _DangerPattern(r"\bdel\s+/s\s+/q", CommandThreatLevel.DANGER, "Windows 递归强制删除"),
        _DangerPattern(r"\brd\s+/s\s+/q", CommandThreatLevel.DANGER, "Windows 递归强制删除目录"),
    ]

    ENCODING_PATTERNS: list[_DangerPattern] = [
        _DangerPattern(r"\bbase64\s+(-d|--decode)\b", CommandThreatLevel.WARNING, "base64 解码"),
        _DangerPattern(r"\bxxd\s+(-r|--revert)\b", CommandThreatLevel.WARNING, "xxd 反向解码"),
        _DangerPattern(r"printf\s+.*\\x[0-9a-fA-F]{2}", CommandThreatLevel.WARNING, "printf 十六进制转义"),
        _DangerPattern(r"\$'[^']*\\x[0-9a-fA-F]{2}", CommandThreatLevel.WARNING, "bash 十六进制转义"),
        _DangerPattern(r"\$'[^']*\\[0-7]{3}", CommandThreatLevel.WARNING, "bash 八进制转义"),
    ]

    SHELL_STRUCTURE_PATTERNS: dict[str, str] = {
        "pipe": r"\|",
        "subshell": r"\$\([^)]+\)",
        "command_substitution": r"`[^`]+`",
        "eval": r"\beval\b",
        "exec": r"\bexec\b",
    }

    _THREAT_ORDER: list[CommandThreatLevel] = [
        CommandThreatLevel.SAFE,
        CommandThreatLevel.WARNING,
        CommandThreatLevel.DANGER,
        CommandThreatLevel.CRITICAL,
    ]

    def analyze(self, command: str) -> CommandAnalysis:
        """综合分析命令的安全威胁。

        Args:
            command: 要分析的命令字符串。

        Returns:
            命令分析结果。
        """
        danger_matches = self._match_danger_patterns(command)
        encoding_detected, decoded_commands, decoded_danger_matches = self._detect_encoding(command)
        shell_structure = self._analyze_shell_structure(command)

        all_danger_matches = danger_matches + decoded_danger_matches
        patterns_matched = [desc for _, _, desc in all_danger_matches]

        has_privilege_escalation = any(
            desc in ("以超级用户执行", "切换用户")
            for _, _, desc in all_danger_matches
        )
        has_network_access = any(
            "远程脚本执行" in desc
            for _, _, desc in all_danger_matches
        )
        has_file_destruction = any(
            level in (CommandThreatLevel.CRITICAL, CommandThreatLevel.DANGER)
            and "超级用户" not in desc
            and "切换用户" not in desc
            and "后台持久运行" not in desc
            and "脱离终端控制" not in desc
            for _, level, desc in all_danger_matches
        )

        threat_level = self._compute_threat_level(
            all_danger_matches, encoding_detected, shell_structure
        )

        analysis = CommandAnalysis(
            threat_level=threat_level,
            patterns_matched=patterns_matched,
            decoded_commands=decoded_commands,
            has_encoding=encoding_detected,
            has_shell_escape=any(shell_structure.values()),
            has_privilege_escalation=has_privilege_escalation,
            has_network_access=has_network_access,
            has_file_destruction=has_file_destruction,
        )

        logger.debug(f"命令分析完成: threat={threat_level.value}, patterns={patterns_matched}")
        return analysis

    def _match_danger_patterns(self, command: str) -> list[tuple]:
        """匹配危险模式。

        Args:
            command: 要检查的命令字符串。

        Returns:
            匹配到的 (pattern, threat_level, description) 列表。
        """
        matches: list[tuple] = []
        for dp in self.DANGER_PATTERNS:
            if re.search(dp.pattern, command, re.IGNORECASE):
                matches.append((dp.pattern, dp.threat_level, dp.description))
        return matches

    def _detect_encoding(self, command: str) -> tuple[bool, list[str], list[tuple]]:
        """检测编码绕过。

        识别 base64 等编码方式，并尝试解码以检查是否包含危险命令。

        Args:
            command: 要检查的命令字符串。

        Returns:
            (是否检测到编码, 解码后的命令列表, 解码后的危险匹配列表) 元组。
        """
        detected = False
        decoded_commands: list[str] = []
        decoded_danger_matches: list[tuple] = []

        for ep in self.ENCODING_PATTERNS:
            if re.search(ep.pattern, command, re.IGNORECASE):
                detected = True
                break

        base64_match = re.search(
            r"echo\s+([A-Za-z0-9+/=]{4,})\s*\|\s*base64\s+(-d|--decode)",
            command,
        )
        if base64_match:
            detected = True
            encoded = base64_match.group(1)
            try:
                decoded = base64.b64decode(encoded).decode("utf-8", errors="replace")
                decoded_commands.append(decoded)
                sub_matches = self._match_danger_patterns(decoded)
                if sub_matches:
                    decoded_danger_matches.extend(sub_matches)
                    for _, _, desc in sub_matches:
                        decoded_commands.append(f"[编码内含危险命令] {desc}")
            except Exception:
                logger.debug(f"base64 解码失败: {encoded[:32]}...")

        pipe_base64 = re.search(r"\|\s*base64\s+(-d|--decode)", command)
        if pipe_base64 and not base64_match:
            detected = True
            before_pipe = command.split("|")[0].strip()
            segments = re.findall(r"[A-Za-z0-9+/=]{16,}", before_pipe)
            for segment in segments:
                try:
                    decoded = base64.b64decode(segment).decode("utf-8", errors="replace")
                    decoded_commands.append(decoded)
                    sub_matches = self._match_danger_patterns(decoded)
                    if sub_matches:
                        decoded_danger_matches.extend(sub_matches)
                        for _, _, desc in sub_matches:
                            decoded_commands.append(f"[编码内含危险命令] {desc}")
                except Exception:
                    pass

        return detected, decoded_commands, decoded_danger_matches

    def _analyze_shell_structure(self, command: str) -> dict[str, bool]:
        """分析 shell 结构。

        检测管道、子 shell、命令替换、eval/exec 等结构。

        Args:
            command: 要分析的命令字符串。

        Returns:
            各 shell 结构是否存在的结果字典。
        """
        result: dict[str, bool] = {}
        for name, pattern in self.SHELL_STRUCTURE_PATTERNS.items():
            result[name] = bool(re.search(pattern, command))
        return result

    def _compute_threat_level(
        self,
        danger_matches: list[tuple],
        encoding_detected: bool,
        shell_structure: dict[str, bool],
    ) -> CommandThreatLevel:
        """综合评级威胁等级。

        评级规则：
        - 任一 critical 匹配 → critical
        - 任一 danger 匹配 → danger
        - 编码绕过 + 任何匹配 → 提升 1 级
        - shell escape + 危险命令 → 提升 1 级
        - 仅 warning → warning
        - 无匹配 → safe

        Args:
            danger_matches: 危险模式匹配列表。
            encoding_detected: 是否检测到编码绕过。
            shell_structure: shell 结构分析结果。

        Returns:
            综合威胁等级。
        """
        if not danger_matches:
            if encoding_detected:
                return CommandThreatLevel.WARNING
            return CommandThreatLevel.SAFE

        levels = [level for _, level, _ in danger_matches]
        has_shell_escape = any(shell_structure.values())

        if CommandThreatLevel.CRITICAL in levels:
            base_level = CommandThreatLevel.CRITICAL
        elif CommandThreatLevel.DANGER in levels:
            base_level = CommandThreatLevel.DANGER
        else:
            base_level = CommandThreatLevel.WARNING

        current_idx = self._THREAT_ORDER.index(base_level)

        if encoding_detected:
            has_non_warning = any(
                level in (CommandThreatLevel.DANGER, CommandThreatLevel.CRITICAL)
                for level in levels
            )
            if has_non_warning or base_level != CommandThreatLevel.SAFE:
                current_idx = min(current_idx + 1, len(self._THREAT_ORDER) - 1)

        if has_shell_escape:
            has_dangerous = any(
                level in (CommandThreatLevel.DANGER, CommandThreatLevel.CRITICAL)
                for level in levels
            )
            if has_dangerous:
                current_idx = min(current_idx + 1, len(self._THREAT_ORDER) - 1)

        return self._THREAT_ORDER[current_idx]
