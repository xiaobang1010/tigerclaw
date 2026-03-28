"""Models RPC 方法。

实现模型列表方法。
"""

from typing import Any

from loguru import logger

from tigerclaw.agents.providers.base import LLMProvider


class ModelsMethod:
    """Models RPC 方法处理器。"""

    def __init__(self, providers: dict[str, LLMProvider] | None = None):
        """初始化 Models 方法。

        Args:
            providers: LLM 提供商字典。
        """
        self.providers = providers or {}

    async def list(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """列出可用模型。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            模型列表。
        """
        provider_name = params.get("provider")

        try:
            models = []

            if provider_name:
                provider = self.providers.get(provider_name)
                if provider:
                    provider_models = await self._get_provider_models(provider_name)
                    models.extend(provider_models)
            else:
                for name in self.providers:
                    provider_models = await self._get_provider_models(name)
                    models.extend(provider_models)

            return {
                "ok": True,
                "models": models,
                "total": len(models),
            }

        except Exception as e:
            logger.error(f"列出模型失败: {e}")
            return {"ok": False, "error": str(e)}

    async def get(self, params: dict[str, Any], _user_info: dict[str, Any]) -> dict[str, Any]:
        """获取模型详情。

        Args:
            params: 方法参数。
            _user_info: 用户信息。

        Returns:
            模型详情。
        """
        model_id = params.get("model")
        if not model_id:
            return {"ok": False, "error": "缺少 model 参数"}

        try:
            provider_name = self._infer_provider(model_id)

            if provider_name not in self.providers:
                return {"ok": False, "error": f"未知的模型提供商: {provider_name}"}

            return {
                "ok": True,
                "model": {
                    "id": model_id,
                    "provider": provider_name,
                    "supports_streaming": True,
                    "supports_tools": True,
                    "supports_vision": self._supports_vision(model_id),
                },
            }

        except Exception as e:
            logger.error(f"获取模型详情失败: {e}")
            return {"ok": False, "error": str(e)}

    async def _get_provider_models(self, provider_name: str) -> list[dict[str, Any]]:
        """获取提供商的模型列表。"""
        default_models = {
            "openai": [
                {"id": "gpt-4o", "name": "GPT-4o", "supports_vision": True},
                {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "supports_vision": True},
                {"id": "gpt-4", "name": "GPT-4", "supports_vision": False},
                {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "supports_vision": False},
                {"id": "o1-preview", "name": "o1 Preview", "supports_vision": False},
                {"id": "o1-mini", "name": "o1 Mini", "supports_vision": False},
            ],
            "anthropic": [
                {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "supports_vision": True},
                {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "supports_vision": True},
                {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "supports_vision": True},
                {"id": "claude-3-sonnet-20240229", "name": "Claude 3 Sonnet", "supports_vision": True},
                {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku", "supports_vision": True},
            ],
            "openrouter": [
                {"id": "openrouter/auto", "name": "Auto (Best)", "supports_vision": True},
                {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet (OR)", "supports_vision": True},
                {"id": "openai/gpt-4o", "name": "GPT-4o (OR)", "supports_vision": True},
                {"id": "google/gemini-pro-1.5", "name": "Gemini Pro 1.5", "supports_vision": True},
                {"id": "meta-llama/llama-3.1-70b-instruct", "name": "Llama 3.1 70B", "supports_vision": False},
            ],
        }

        models = default_models.get(provider_name, [])

        result = []
        for model in models:
            result.append({
                "id": model["id"],
                "name": model["name"],
                "provider": provider_name,
                "supports_streaming": True,
                "supports_tools": True,
                "supports_vision": model.get("supports_vision", False),
            })

        return result

    def _infer_provider(self, model_id: str) -> str:
        """根据模型 ID 推断提供商。"""
        if model_id.startswith("gpt") or model_id.startswith("o1") or model_id.startswith("o3"):
            return "openai"
        elif model_id.startswith("claude"):
            return "anthropic"
        elif "/" in model_id:
            return "openrouter"
        return "openai"

    def _supports_vision(self, model_id: str) -> bool:
        """检查模型是否支持视觉。"""
        vision_models = [
            "gpt-4o", "gpt-4-turbo", "gpt-4-vision",
            "claude-3", "claude-3.5",
            "gemini", "openrouter/auto",
        ]
        return any(vm in model_id.lower() for vm in vision_models)


async def handle_models_list(
    params: dict[str, Any],
    user_info: dict[str, Any],
    providers: dict[str, LLMProvider] | None = None,
) -> dict[str, Any]:
    """处理 models.list RPC 方法调用。"""
    method = ModelsMethod(providers)
    return await method.list(params, user_info)


async def handle_models_get(
    params: dict[str, Any],
    user_info: dict[str, Any],
    providers: dict[str, LLMProvider] | None = None,
) -> dict[str, Any]:
    """处理 models.get RPC 方法调用。"""
    method = ModelsMethod(providers)
    return await method.get(params, user_info)
