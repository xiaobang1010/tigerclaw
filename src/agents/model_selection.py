"""模型选择系统模块。

提供模型引用解析、别名管理和配置验证功能。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelRef:
    """模型引用。

    表示一个唯一的模型标识，由 provider 和 model 组成。

    Attributes:
        provider: 提供商标识符。
        model: 模型标识符。
    """

    provider: str
    model: str


@dataclass
class ModelAliasIndex:
    """模型别名索引。

    用于快速查找模型别名和反向映射。

    Attributes:
        by_alias: 别名到模型引用的映射。
        by_key: 模型键到别名列表的反向映射。
    """

    by_alias: dict[str, ModelRef] = field(default_factory=dict)
    by_key: dict[str, list[str]] = field(default_factory=dict)


DEFAULT_PROVIDER = "anthropic"
"""默认提供商标识符。"""

DEFAULT_MODEL = "claude-opus-4-6"
"""默认模型标识符。"""


def model_key(provider: str, model: str) -> str:
    """生成模型键。

    将 provider 和 model 组合成 "provider/model" 格式的唯一键。

    Args:
        provider: 提供商标识符。
        model: 模型标识符。

    Returns:
        "provider/model" 格式的键。
    """
    return f"{provider}/{model}"


def parse_model_ref(raw: str, default_provider: str) -> ModelRef | None:
    """解析模型引用字符串。

    支持两种格式：
    - 完整格式: "provider/model"
    - 裸模型 ID: "model"（使用默认 provider）

    Args:
        raw: 原始模型引用字符串。
        default_provider: 默认提供商标识符。

    Returns:
        解析后的 ModelRef，如果解析失败返回 None。
    """
    if not raw or not raw.strip():
        return None

    raw = raw.strip()

    if "/" in raw:
        parts = raw.split("/", 1)
        if len(parts) != 2:
            return None
        provider, model = parts
        if not provider or not model:
            return None
        return ModelRef(provider=normalize_provider_id(provider), model=model.strip())

    return ModelRef(provider=default_provider, model=raw)


def normalize_provider_id(provider: str) -> str:
    """标准化 provider ID。

    将 provider ID 转换为小写并去除首尾空格。

    Args:
        provider: 原始 provider ID。

    Returns:
        标准化后的 provider ID。
    """
    if not provider:
        return ""
    return provider.strip().lower()


def build_model_alias_index(cfg: dict) -> ModelAliasIndex:
    """从配置构建模型别名索引。

    从 cfg.agents.defaults.models 中提取别名信息构建索引。
    每个模型配置可包含 alias 字段（字符串或字符串列表）。

    Args:
        cfg: 配置字典。

    Returns:
        构建好的 ModelAliasIndex。
    """
    index = ModelAliasIndex()

    agents_cfg = cfg.get("agents", {})
    if not isinstance(agents_cfg, dict):
        return index

    defaults_cfg = agents_cfg.get("defaults", {})
    if not isinstance(defaults_cfg, dict):
        return index

    models_cfg = defaults_cfg.get("models", [])
    if not isinstance(models_cfg, list):
        return index

    for model_entry in models_cfg:
        if not isinstance(model_entry, dict):
            continue

        provider = model_entry.get("provider", DEFAULT_PROVIDER)
        model_id = model_entry.get("id") or model_entry.get("model")
        if not model_id:
            continue

        provider = normalize_provider_id(provider)
        key = model_key(provider, model_id)
        ref = ModelRef(provider=provider, model=model_id)

        alias_value = model_entry.get("alias")
        aliases: list[str] = []

        if isinstance(alias_value, str):
            aliases = [alias_value]
        elif isinstance(alias_value, list):
            aliases = [a for a in alias_value if isinstance(a, str)]

        for alias in aliases:
            alias = alias.strip()
            if alias:
                index.by_alias[alias] = ref
                if key not in index.by_key:
                    index.by_key[key] = []
                index.by_key[key].append(alias)

    return index


def resolve_model_ref_from_string(
    raw: str,
    default_provider: str,
    alias_index: ModelAliasIndex | None = None,
) -> ModelRef | None:
    """从字符串解析模型引用。

    解析顺序：
    1. 先尝试别名匹配（如果提供了 alias_index）
    2. 再解析 provider/model 格式

    Args:
        raw: 原始模型引用字符串。
        default_provider: 默认提供商标识符。
        alias_index: 可选的别名索引。

    Returns:
        解析后的 ModelRef，如果解析失败返回 None。
    """
    if not raw or not raw.strip():
        return None

    raw = raw.strip()

    if alias_index and raw in alias_index.by_alias:
        return alias_index.by_alias[raw]

    return parse_model_ref(raw, default_provider)


def build_allowed_model_set(cfg: dict, default_provider: str) -> tuple[set[str], bool]:
    """构建允许的模型集合。

    从 cfg.agents.defaults.models 中提取允许的模型列表。
    如果没有配置 models，返回空集合和 True（允许任意模型）。

    Args:
        cfg: 配置字典。
        default_provider: 默认提供商标识符。

    Returns:
        元组 (allowed_keys, allow_any)：
        - allowed_keys: 允许的模型键集合
        - allow_any: 是否允许任意模型
    """
    agents_cfg = cfg.get("agents", {})
    if not isinstance(agents_cfg, dict):
        return set(), True

    defaults_cfg = agents_cfg.get("defaults", {})
    if not isinstance(defaults_cfg, dict):
        return set(), True

    models_cfg = defaults_cfg.get("models")
    if models_cfg is None:
        return set(), True

    if not isinstance(models_cfg, list) or len(models_cfg) == 0:
        return set(), True

    allowed_keys: set[str] = set()

    for model_entry in models_cfg:
        if not isinstance(model_entry, dict):
            continue

        provider = model_entry.get("provider", default_provider)
        model_id = model_entry.get("id") or model_entry.get("model")
        if not model_id:
            continue

        provider = normalize_provider_id(provider)
        key = model_key(provider, model_id)
        allowed_keys.add(key)

    return allowed_keys, False


def resolve_configured_model_ref(
    cfg: dict,
    default_provider: str,
    default_model: str,
) -> ModelRef:
    """从配置解析主模型引用。

    从 cfg.agents.defaults.model 解析主模型引用。
    如果未配置或解析失败，使用默认值。

    Args:
        cfg: 配置字典。
        default_provider: 默认提供商标识符。
        default_model: 默认模型标识符。

    Returns:
        解析后的 ModelRef。
    """
    agents_cfg = cfg.get("agents", {})
    if not isinstance(agents_cfg, dict):
        return ModelRef(provider=default_provider, model=default_model)

    defaults_cfg = agents_cfg.get("defaults", {})
    if not isinstance(defaults_cfg, dict):
        return ModelRef(provider=default_provider, model=default_model)

    model_value = defaults_cfg.get("model")
    if not model_value or not isinstance(model_value, str):
        return ModelRef(provider=default_provider, model=default_model)

    alias_index = build_model_alias_index(cfg)
    ref = resolve_model_ref_from_string(model_value, default_provider, alias_index)

    if ref:
        return ref

    return ModelRef(provider=default_provider, model=default_model)
