"""飞书渠道模块。

提供飞书（Feishu/Lark）消息渠道的完整实现，
包括入站 Webhook 处理、出站消息发送和配置向导。
"""

from channels.feishu.outbound import FeishuApiClient, create_feishu_outbound_handler

__all__ = [
    "FeishuApiClient",
    "create_feishu_outbound_handler",
]
