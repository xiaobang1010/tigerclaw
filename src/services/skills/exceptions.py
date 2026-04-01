"""Skills 服务异常定义。"""


class SkillError(Exception):
    """Skill 相关错误的基类。"""

    pass


class SkillNotFoundError(SkillError):
    """Skill 未找到。"""

    def __init__(self, skill_name: str) -> None:
        """初始化异常。

        Args:
            skill_name: 未找到的 skill 名称。
        """
        self.skill_name = skill_name
        super().__init__(f"Skill not found: {skill_name}")


class SkillLoadError(SkillError):
    """Skill 加载失败。"""

    def __init__(self, skill_name: str, reason: str) -> None:
        """初始化异常。

        Args:
            skill_name: 加载失败的 skill 名称。
            reason: 失败原因。
        """
        self.skill_name = skill_name
        self.reason = reason
        super().__init__(f"Failed to load skill '{skill_name}': {reason}")


class SkillValidationError(SkillError):
    """Skill 验证失败。"""

    def __init__(self, skill_name: str, errors: list[str]) -> None:
        """初始化异常。

        Args:
            skill_name: 验证失败的 skill 名称。
            errors: 验证错误列表。
        """
        self.skill_name = skill_name
        self.errors = errors
        error_msg = "; ".join(errors)
        super().__init__(f"Skill validation failed for '{skill_name}': {error_msg}")


class SkillPathError(SkillError):
    """Skill 路径错误。"""

    def __init__(self, path: str, reason: str) -> None:
        """初始化异常。

        Args:
            path: 问题路径。
            reason: 错误原因。
        """
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid skill path '{path}': {reason}")


class SkillFilterError(SkillError):
    """Skill 过滤器错误。"""

    def __init__(self, filter_expr: str, reason: str) -> None:
        """初始化异常。

        Args:
            filter_expr: 过滤表达式。
            reason: 错误原因。
        """
        self.filter_expr = filter_expr
        self.reason = reason
        super().__init__(f"Invalid skill filter '{filter_expr}': {reason}")
