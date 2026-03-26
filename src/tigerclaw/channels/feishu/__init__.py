"""飞书渠道模块

提供飞书（Lark）消息渠道的完整实现，包括：
- Webhook 消息接收
- 消息发送
- 事件处理
- 签名验证
"""

from .channel import FeishuChannel, FeishuConfig

__all__ = ["FeishuChannel", "FeishuConfig"]
