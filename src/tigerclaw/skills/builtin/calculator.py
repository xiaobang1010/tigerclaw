"""计算器技能

提供数学计算功能的技能示例。
"""

import math
from typing import Any

from ..base import (
    SkillBase,
    SkillCategory,
    SkillContext,
    SkillDefinition,
    SkillParameter,
    SkillResult,
)


class CalculatorSkill(SkillBase):
    """计算器技能

    执行数学计算并返回结果。
    支持基本运算和常用数学函数。
    """

    SAFE_FUNCTIONS = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "floor": math.floor,
        "ceil": math.ceil,
        "pi": math.pi,
        "e": math.e,
    }

    def __init__(self) -> None:
        super().__init__(SkillDefinition(
            name="calculator",
            description="执行数学计算，支持基本运算和常用数学函数",
            parameters=[
                SkillParameter(
                    name="expression",
                    type="string",
                    description="数学表达式，如 '2 + 3 * 4' 或 'sqrt(16)'",
                    required=True,
                ),
                SkillParameter(
                    name="precision",
                    type="integer",
                    description="结果精度（小数位数）",
                    required=False,
                    default=2,
                    min_value=0,
                    max_value=10,
                ),
            ],
            category=SkillCategory.COMPUTATION,
            timeout_ms=5000,
        ))

    async def _execute_impl(
        self,
        arguments: dict[str, Any],
        context: SkillContext
    ) -> SkillResult:
        expression = arguments.get("expression", "")
        precision = arguments.get("precision", 2)

        if not expression:
            return SkillResult.fail("表达式不能为空")

        try:
            result = self._evaluate(expression)
            rounded_result = round(result, precision) if isinstance(result, float) else result

            return SkillResult.ok(
                data={
                    "expression": expression,
                    "result": rounded_result,
                    "precision": precision,
                }
            )
        except Exception as e:
            return SkillResult.fail(f"计算错误: {str(e)}")

    def _evaluate(self, expression: str) -> float | int:
        """安全地计算数学表达式

        使用受限的命名空间来执行表达式，只允许安全的数学函数。
        """
        safe_dict = dict(self.SAFE_FUNCTIONS)

        safe_dict["__builtins__"] = {}

        try:
            result = eval(expression, safe_dict, {})
            if isinstance(result, (int, float)):
                return result
            raise ValueError("表达式结果不是数值")
        except NameError as e:
            raise ValueError(f"不支持的函数或变量: {e}")
        except SyntaxError as e:
            raise ValueError(f"表达式语法错误: {e}")


skill = CalculatorSkill()
