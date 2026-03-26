"""模型目录模块

提供模型信息管理功能，包括：
- 模型信息查询
- 上下文窗口限制
- 模型能力查询
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelCapability(Enum):
    """模型能力"""
    CHAT = "chat"
    VISION = "vision"
    TOOLS = "tools"
    STREAMING = "streaming"
    JSON_MODE = "json_mode"
    REASONING = "reasoning"


@dataclass
class ModelInfo:
    """模型信息"""
    id: str
    name: str
    provider: str
    context_window: int = 4096
    max_output_tokens: int = 4096
    capabilities: list[ModelCapability] = field(default_factory=list)
    pricing: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def supports(self, capability: ModelCapability) -> bool:
        return capability in self.capabilities

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "capabilities": [c.value for c in self.capabilities],
            "pricing": self.pricing,
        }


DEFAULT_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="gpt-4o",
        name="GPT-4o",
        provider="openai",
        context_window=128000,
        max_output_tokens=16384,
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.VISION,
            ModelCapability.TOOLS,
            ModelCapability.STREAMING,
            ModelCapability.JSON_MODE,
        ],
        pricing={"input": 2.5, "output": 10.0},
    ),
    ModelInfo(
        id="gpt-4-turbo",
        name="GPT-4 Turbo",
        provider="openai",
        context_window=128000,
        max_output_tokens=4096,
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.VISION,
            ModelCapability.TOOLS,
            ModelCapability.STREAMING,
            ModelCapability.JSON_MODE,
        ],
        pricing={"input": 10.0, "output": 30.0},
    ),
    ModelInfo(
        id="gpt-3.5-turbo",
        name="GPT-3.5 Turbo",
        provider="openai",
        context_window=16385,
        max_output_tokens=4096,
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.TOOLS,
            ModelCapability.STREAMING,
            ModelCapability.JSON_MODE,
        ],
        pricing={"input": 0.5, "output": 1.5},
    ),
    ModelInfo(
        id="claude-3-5-sonnet-20241022",
        name="Claude 3.5 Sonnet",
        provider="anthropic",
        context_window=200000,
        max_output_tokens=8192,
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.VISION,
            ModelCapability.TOOLS,
            ModelCapability.STREAMING,
        ],
        pricing={"input": 3.0, "output": 15.0},
    ),
    ModelInfo(
        id="claude-3-opus-20240229",
        name="Claude 3 Opus",
        provider="anthropic",
        context_window=200000,
        max_output_tokens=4096,
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.VISION,
            ModelCapability.TOOLS,
            ModelCapability.STREAMING,
        ],
        pricing={"input": 15.0, "output": 75.0},
    ),
    ModelInfo(
        id="minimax-text-01",
        name="MiniMax Text 01",
        provider="minimax",
        context_window=245000,
        max_output_tokens=16384,
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.TOOLS,
            ModelCapability.STREAMING,
        ],
        pricing={"input": 0.3, "output": 1.0},
    ),
]


class ModelCatalog:
    """模型目录"""

    def __init__(self):
        self._models: dict[str, ModelInfo] = {}
        self._provider_models: dict[str, list[str]] = {}
        self._load_default_models()

    def _load_default_models(self) -> None:
        for model in DEFAULT_MODELS:
            self.register(model)

    def register(self, model: ModelInfo) -> None:
        self._models[model.id] = model
        if model.provider not in self._provider_models:
            self._provider_models[model.provider] = []
        if model.id not in self._provider_models[model.provider]:
            self._provider_models[model.provider].append(model.id)

    def unregister(self, model_id: str) -> bool:
        if model_id not in self._models:
            return False
        model = self._models.pop(model_id)
        if model.provider in self._provider_models:
            self._provider_models[model.provider] = [
                m for m in self._provider_models[model.provider] if m != model_id
            ]
        return True

    def get(self, model_id: str) -> ModelInfo | None:
        return self._models.get(model_id)

    def get_context_window(self, model_id: str) -> int:
        model = self.get(model_id)
        return model.context_window if model else 4096

    def get_max_output_tokens(self, model_id: str) -> int:
        model = self.get(model_id)
        return model.max_output_tokens if model else 4096

    def supports(self, model_id: str, capability: ModelCapability) -> bool:
        model = self.get(model_id)
        return model.supports(capability) if model else False

    def list_all(self) -> list[ModelInfo]:
        return list(self._models.values())

    def list_by_provider(self, provider: str) -> list[ModelInfo]:
        model_ids = self._provider_models.get(provider, [])
        return [self._models[mid] for mid in model_ids if mid in self._models]

    def list_providers(self) -> list[str]:
        return list(self._provider_models.keys())

    def search(self, query: str) -> list[ModelInfo]:
        query_lower = query.lower()
        return [
            m for m in self._models.values()
            if query_lower in m.id.lower() or query_lower in m.name.lower()
        ]

    def get_info(self) -> dict[str, Any]:
        return {
            "total_models": len(self._models),
            "providers": {
                provider: len(models)
                for provider, models in self._provider_models.items()
            },
        }


_catalog: ModelCatalog | None = None


def get_catalog() -> ModelCatalog:
    global _catalog
    if _catalog is None:
        _catalog = ModelCatalog()
    return _catalog
