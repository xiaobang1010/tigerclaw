"""Cron 表达式解析。

支持标准 Cron 表达式的解析和匹配。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class CronField:
    """Cron 字段。"""

    name: str
    min_value: int
    max_value: int
    values: set[int]


class CronExpression:
    """Cron 表达式解析器。

    支持标准 5 字段 Cron 表达式：
    分钟 小时 日 月 星期

    例如：
    - "*/5 * * * *" - 每 5 分钟
    - "0 9 * * 1-5" - 工作日早上 9 点
    - "0 0 1 * *" - 每月 1 号午夜
    """

    MONTH_NAMES = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    DAY_NAMES = {
        "sun": 0, "mon": 1, "tue": 2, "wed": 3,
        "thu": 4, "fri": 5, "sat": 6,
    }

    def __init__(self, expression: str):
        """初始化 Cron 表达式。

        Args:
            expression: Cron 表达式字符串。
        """
        self.expression = expression
        self._fields: list[CronField] = []
        self._parse()

    def _parse(self) -> None:
        """解析 Cron 表达式。"""
        parts = self.expression.strip().split()

        if len(parts) != 5:
            raise ValueError(f"无效的 Cron 表达式: {self.expression}，需要 5 个字段")

        field_configs = [
            ("minute", 0, 59),
            ("hour", 0, 23),
            ("day", 1, 31),
            ("month", 1, 12),
            ("weekday", 0, 6),
        ]

        for i, (name, min_val, max_val) in enumerate(field_configs):
            values = self._parse_field(parts[i], min_val, max_val, name)
            self._fields.append(CronField(
                name=name,
                min_value=min_val,
                max_value=max_val,
                values=values,
            ))

    def _parse_field(self, field: str, min_val: int, max_val: int, name: str) -> set[int]:
        """解析单个字段。

        Args:
            field: 字段字符串。
            min_val: 最小值。
            max_val: 最大值。
            name: 字段名称。

        Returns:
            允许的值集合。
        """
        if name == "month":
            field = self._replace_names(field, self.MONTH_NAMES)
        elif name == "weekday":
            field = self._replace_names(field, self.DAY_NAMES)

        if field == "*":
            return set(range(min_val, max_val + 1))

        values = set()

        for part in field.split(","):
            part = part.strip()

            if "/" in part:
                range_part, step_part = part.split("/", 1)
                step = int(step_part)

                if range_part == "*":
                    start, end = min_val, max_val
                elif "-" in range_part:
                    start, end = map(int, range_part.split("-"))
                else:
                    start = end = int(range_part)

                for v in range(start, end + 1, step):
                    if min_val <= v <= max_val:
                        values.add(v)

            elif "-" in part:
                start, end = map(int, part.split("-"))
                for v in range(start, end + 1):
                    if min_val <= v <= max_val:
                        values.add(v)

            else:
                v = int(part)
                if min_val <= v <= max_val:
                    values.add(v)

        return values

    def _replace_names(self, field: str, names: dict[str, int]) -> str:
        """替换名称为数字。

        Args:
            field: 字段字符串。
            names: 名称到数字的映射。

        Returns:
            替换后的字段字符串。
        """
        result = field.lower()
        for name, value in names.items():
            result = result.replace(name, str(value))
        return result

    def matches(self, dt: datetime) -> bool:
        """检查时间是否匹配 Cron 表达式。

        Args:
            dt: 要检查的时间。

        Returns:
            如果匹配返回 True。
        """
        values = [
            dt.minute,
            dt.hour,
            dt.day,
            dt.month,
            dt.weekday(),
        ]

        return all(value in field.values for field, value in zip(self._fields, values))

    def get_next_run(self, after: datetime | None = None) -> datetime:
        """获取下一次运行时间。

        Args:
            after: 起始时间。

        Returns:
            下一次运行时间。
        """
        if after is None:
            after = datetime.now()

        next_time = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

        for _ in range(366 * 24 * 60):
            if self.matches(next_time):
                return next_time
            next_time += timedelta(minutes=1)

        raise ValueError("无法找到下一次运行时间")

    def get_next_runs(self, after: datetime | None = None, count: int = 5) -> list[datetime]:
        """获取接下来多次运行时间。

        Args:
            after: 起始时间。
            count: 数量。

        Returns:
            运行时间列表。
        """
        if after is None:
            after = datetime.now()

        runs = []
        current = after

        for _ in range(count):
            next_run = self.get_next_run(current)
            runs.append(next_run)
            current = next_run

        return runs

    def __str__(self) -> str:
        return self.expression

    def __repr__(self) -> str:
        return f"CronExpression({self.expression!r})"


def parse_cron(expression: str) -> CronExpression:
    """解析 Cron 表达式。

    Args:
        expression: Cron 表达式字符串。

    Returns:
        CronExpression 实例。
    """
    return CronExpression(expression)


def is_valid_cron(expression: str) -> bool:
    """检查是否为有效的 Cron 表达式。

    Args:
        expression: Cron 表达式字符串。

    Returns:
        如果有效返回 True。
    """
    try:
        CronExpression(expression)
        return True
    except (ValueError, TypeError):
        return False
