"""内置技能模块

提供常用的内置技能实现。
"""

from .calculator import CalculatorSkill
from .web_search import WebSearchSkill

__all__ = [
    "CalculatorSkill",
    "WebSearchSkill",
]
