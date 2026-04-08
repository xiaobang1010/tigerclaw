"""飞书渠道配置向导。

提供飞书渠道的配置引导功能，包括：
- 凭证定义
- 配置状态检查
- 交互式配置流程
"""

from __future__ import annotations

from typing import Any

from loguru import logger


class FeishuSetupWizard:
    """飞书渠道配置向导。

    引导用户完成飞书应用的配置，包括凭证输入和状态验证。
    """

    def get_credentials(self) -> list[dict[str, Any]]:
        """获取凭证定义列表。

        返回飞书应用所需的凭证字段定义，
        用于自动生成配置界面。

        Returns:
            凭证定义列表，每项包含 id、label、required、secret 等字段。
        """
        return [
            {
                "id": "app_id",
                "label": "App ID",
                "required": True,
                "secret": False,
            },
            {
                "id": "app_secret",
                "label": "App Secret",
                "required": True,
                "secret": True,
            },
            {
                "id": "verification_token",
                "label": "Verification Token",
                "required": False,
                "secret": False,
            },
            {
                "id": "encrypt_key",
                "label": "Encrypt Key",
                "required": False,
                "secret": True,
            },
        ]

    def get_status(self, config: dict[str, Any]) -> dict[str, Any]:
        """检查飞书配置状态。

        验证配置中是否包含必需的凭证信息。

        Args:
            config: 飞书配置字典。

        Returns:
            状态字典，包含 complete 和 missing 字段。
        """
        required_fields = ["app_id", "app_secret"]
        missing = [
            field for field in required_fields if not config.get(field, "").strip()
        ]

        return {
            "complete": len(missing) == 0,
            "missing": missing,
        }

    async def configure(self, interactive: bool = True) -> dict[str, Any]:
        """执行配置流程。

        在交互模式下，通过命令行提示引导用户输入凭证。
        非交互模式下返回空配置。

        Args:
            interactive: 是否使用交互模式。

        Returns:
            配置字典。
        """
        if not interactive:
            return {}

        config: dict[str, Any] = {}
        credentials = self.get_credentials()

        for cred in credentials:
            cred_id = cred["id"]
            label = cred["label"]
            required = cred.get("required", False)

            try:
                prompt_text = f"{label}: "
                value = input(prompt_text).strip()
            except (EOFError, KeyboardInterrupt):
                if required:
                    logger.warning(f"缺少必需配置项: {label}")
                    return config
                continue

            if not value and required:
                logger.warning(f"缺少必需配置项: {label}")
                return config

            if value:
                config[cred_id] = value

        status = self.get_status(config)
        if status["complete"]:
            logger.info("飞书渠道配置完成")
        else:
            logger.warning(f"飞书渠道配置不完整，缺少: {status['missing']}")

        return config
