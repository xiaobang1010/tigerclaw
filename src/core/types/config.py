"""配置类型定义。

本模块定义了 TigerClaw 中使用的配置相关类型，
包括网关配置、模型配置、渠道配置等。
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.types.providers import AgentsConfig, ModelsConfig


class BindMode(StrEnum):
    """绑定模式枚举。"""

    LOOPBACK = "loopback"
    LAN = "lan"
    TAILNET = "tailnet"
    AUTO = "auto"


class LogLevel(StrEnum):
    """日志级别枚举。"""

    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuthType(StrEnum):
    """认证类型枚举。"""

    TOKEN = "token"
    PAIRING_CODE = "pairing_code"
    OAUTH = "oauth"
    TAILSCALE = "tailscale"


class GatewayAuthMode(StrEnum):
    """网关认证模式枚举。"""

    NONE = "none"
    TOKEN = "token"
    PASSWORD = "password"
    TRUSTED_PROXY = "trusted-proxy"


class ReloadMode(StrEnum):
    """重载模式枚举。

    定义 Gateway 配置变更后的重载策略。

    Attributes:
        OFF: 禁用热重载，需要手动重启
        HOT: 热重载，无需重启服务
        RESTART: 自动重启服务
        HYBRID: 混合模式，根据变更类型自动选择
    """

    OFF = "off"
    HOT = "hot"
    RESTART = "restart"
    HYBRID = "hybrid"


class TokenConfig(BaseModel):
    """Token 配置。"""

    name: str = Field(..., description="Token名称")
    token: str = Field(..., description="Token值")
    description: str | None = Field(None, description="描述")


class TrustedProxyConfig(BaseModel):
    """受信任代理配置。"""

    user_header: str = Field(default="X-User", description="用户头名称")
    required_headers: list[str] = Field(default_factory=list, description="必需的请求头")
    allow_users: list[str] = Field(default_factory=list, description="允许的用户列表")


class RateLimitConfig(BaseModel):
    """速率限制配置。

    用于控制认证失败后的锁定策略，防止暴力破解攻击。

    Attributes:
        max_attempts: 在滑动窗口内允许的最大失败尝试次数
        window_ms: 滑动窗口时间（毫秒），用于计算失败次数
        lockout_ms: 达到最大失败次数后的锁定时间（毫秒）
        exempt_loopback: 是否豁免回环地址（localhost）的速率限制
    """

    max_attempts: int = Field(default=10, description="最大尝试次数")
    window_ms: int = Field(default=60000, description="滑动窗口时间（毫秒）")
    lockout_ms: int = Field(default=300000, description="锁定时间（毫秒）")
    exempt_loopback: bool = Field(default=True, description="是否豁免回环地址")


class AuthConfig(BaseModel):
    """认证配置。

    定义 Gateway 的认证方式和相关参数，支持多种认证模式。

    Attributes:
        mode: 认证模式（none/token/password/trusted-proxy）
        token: 认证 Token（mode 为 token 时使用）
        password: 认证密码（mode 为 password 时使用）
        tokens: Token 列表，支持多个 Token 配置
        pairing_enabled: 是否启用配对码认证
        pairing_timeout_ms: 配对码超时时间（毫秒）
        allow_tailscale: 是否允许 Tailscale 网络认证
        trusted_proxy: 受信任代理配置（mode 为 trusted-proxy 时使用）
        rate_limit: 速率限制配置，防止暴力破解
    """

    mode: GatewayAuthMode = Field(default=GatewayAuthMode.TOKEN, description="认证模式")
    token: str | None = Field(None, description="认证Token")
    password: str | None = Field(None, description="认证密码")
    tokens: list[TokenConfig] = Field(default_factory=list, description="Token列表")
    pairing_enabled: bool = Field(default=True, description="是否启用配对")
    pairing_timeout_ms: int = Field(default=300000, description="配对超时（毫秒）")
    allow_tailscale: bool = Field(default=False, description="是否允许Tailscale认证")
    trusted_proxy: TrustedProxyConfig | None = Field(None, description="受信任代理配置")
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig, description="速率限制配置")

    model_config = {"use_enum_values": True}


class GatewayTlsConfig(BaseModel):
    """Gateway TLS 配置。

    定义 Gateway 的 TLS/HTTPS 安全传输配置。

    Attributes:
        enabled: 是否启用 TLS（HTTPS）
        auto_generate: 证书缺失时是否自动生成自签名证书
        cert_path: PEM 格式证书文件路径
        key_path: PEM 格式私钥文件路径
        ca_path: 可选的 CA 证书路径（用于 mTLS 或自定义根证书）
    """

    enabled: bool = Field(default=False, description="是否启用 TLS")
    auto_generate: bool = Field(default=True, description="证书缺失时是否自动生成自签名证书")
    cert_path: str | None = Field(None, description="PEM 证书文件路径")
    key_path: str | None = Field(None, description="PEM 私钥文件路径")
    ca_path: str | None = Field(None, description="可选的 CA 证书路径（用于 mTLS 或自定义根证书）")


class GatewayReloadConfig(BaseModel):
    """Gateway 重载配置。

    定义配置变更后的重载策略，支持多种重载模式。

    Attributes:
        mode: 重载模式（off/hot/restart/hybrid）
            - off: 禁用热重载，需要手动重启
            - hot: 热重载，无需重启服务
            - restart: 自动重启服务
            - hybrid: 混合模式，根据变更类型自动选择
    """

    mode: ReloadMode = Field(default=ReloadMode.OFF, description="重载模式")

    model_config = {"use_enum_values": True}


class GatewayConfig(BaseModel):
    """Gateway 配置。

    定义 TigerClaw Gateway 的核心配置参数，包括网络绑定、认证、TLS 等。

    Attributes:
        port: 监听端口号（1-65535），默认 18789
        bind: 绑定模式（loopback/lan/tailnet/auto）
        host: 自定义绑定地址（可选，通常由 bind 模式决定）
        cors_origins: CORS 允许的源列表，默认 ["*"]
        tls: TLS/HTTPS 配置
        auth: 认证配置
        reload: 配置重载策略
        trusted_proxies: 受信任的代理地址列表
        control_ui_enabled: 是否启用控制 UI
        openai_chat_completions_enabled: 是否启用 OpenAI 兼容 API
        allow_real_ip_fallback: 是否允许 X-Real-IP 后备
    """

    bind: BindMode = Field(default=BindMode.LOOPBACK, description="绑定模式")
    host: str | None = Field(None, description="绑定地址")
    port: int = Field(default=18789, ge=1, le=65535, description="端口号")
    cors_origins: list[str] = Field(default_factory=lambda: ["*"], description="CORS允许的源")
    tls: GatewayTlsConfig = Field(default_factory=GatewayTlsConfig, description="TLS 配置")
    auth: AuthConfig = Field(default_factory=AuthConfig, description="认证配置")
    reload: GatewayReloadConfig = Field(default_factory=GatewayReloadConfig, description="重载配置")
    trusted_proxies: list[str] = Field(default_factory=list, description="受信任的代理地址列表")
    control_ui_enabled: bool = Field(default=True, description="是否启用控制UI")
    openai_chat_completions_enabled: bool = Field(default=True, description="是否启用OpenAI兼容API")
    allow_real_ip_fallback: bool = Field(default=False, description="是否允许X-Real-IP后备")

    model_config = {"use_enum_values": True}


class ModelProvider(StrEnum):
    """模型提供商枚举。"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    GOOGLE = "google"
    OLLAMA = "ollama"
    GROQ = "groq"
    DEEPSEEK = "deepseek"


class AuthProfile(BaseModel):
    """认证配置。"""

    name: str = Field(..., description="配置名称")
    api_key: str | None = Field(None, description="API密钥")
    base_url: str | None = Field(None, description="基础URL")
    oauth_token: str | None = Field(None, description="OAuth令牌")
    headers: dict[str, str] = Field(default_factory=dict, description="额外请求头")


class ModelConfig(BaseModel):
    """模型配置。"""

    id: str = Field(..., description="模型ID")
    provider: ModelProvider = Field(..., description="提供商")
    name: str | None = Field(None, description="显示名称")
    auth_profiles: list[AuthProfile] = Field(default_factory=list, description="认证配置列表")
    context_window: int = Field(default=4096, description="上下文窗口大小")
    supports_vision: bool = Field(default=False, description="是否支持视觉")
    supports_tools: bool = Field(default=True, description="是否支持工具调用")
    supports_streaming: bool = Field(default=True, description="是否支持流式输出")
    max_output_tokens: int | None = Field(None, description="最大输出Token数")
    default_temperature: float = Field(default=0.7, description="默认温度")
    enabled: bool = Field(default=True, description="是否启用")

    model_config = {"use_enum_values": True}


class ChannelConfig(BaseModel):
    """渠道配置基类。"""

    enabled: bool = Field(default=False, description="是否启用")
    name: str | None = Field(None, description="渠道名称")


class FeishuChannelConfig(ChannelConfig):
    """飞书渠道配置。"""

    app_id: str | None = Field(None, description="应用ID")
    app_secret: str | None = Field(None, description="应用密钥")
    verification_token: str | None = Field(None, description="验证Token")
    encrypt_key: str | None = Field(None, description="加密密钥")


class SlackChannelConfig(ChannelConfig):
    """Slack 渠道配置。"""

    bot_token: str | None = Field(None, description="Bot Token")
    app_token: str | None = Field(None, description="App Token")
    signing_secret: str | None = Field(None, description="签名密钥")


class DiscordChannelConfig(ChannelConfig):
    """Discord 渠道配置。"""

    bot_token: str | None = Field(None, description="Bot Token")
    application_id: str | None = Field(None, description="应用ID")


class TelegramChannelConfig(ChannelConfig):
    """Telegram 渠道配置。"""

    bot_token: str | None = Field(None, description="Bot Token")


class ChannelsConfig(BaseModel):
    """渠道配置集合。"""

    feishu: FeishuChannelConfig = Field(default_factory=FeishuChannelConfig, description="飞书配置")
    slack: SlackChannelConfig = Field(default_factory=SlackChannelConfig, description="Slack配置")
    discord: DiscordChannelConfig = Field(
        default_factory=DiscordChannelConfig, description="Discord配置"
    )
    telegram: TelegramChannelConfig = Field(
        default_factory=TelegramChannelConfig, description="Telegram配置"
    )


class AgentConfig(BaseModel):
    """代理配置。"""

    model: str = Field(default="gpt-4", description="使用的模型")
    system_prompt: str | None = Field(None, description="系统提示")
    temperature: float = Field(default=0.7, description="温度参数")
    max_tokens: int | None = Field(None, description="最大Token数")
    enable_tools: bool = Field(default=True, description="是否启用工具")
    failover_enabled: bool = Field(default=True, description="是否启用故障转移")
    max_retries: int = Field(default=3, description="最大重试次数")


class LoggingConfig(BaseModel):
    """日志配置。"""

    level: LogLevel = Field(default=LogLevel.INFO, description="日志级别")
    format: str = Field(
        default="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        description="日志格式",
    )
    file_enabled: bool = Field(default=False, description="是否启用文件日志")
    file_path: str | None = Field(None, description="日志文件路径")
    rotation: str = Field(default="10 MB", description="日志轮转大小")
    retention: str = Field(default="7 days", description="日志保留时间")

    model_config = {"use_enum_values": True}


class TigerClawConfig(BaseModel):
    """TigerClaw 主配置。"""

    gateway: GatewayConfig = Field(default_factory=GatewayConfig, description="Gateway配置")
    models: ModelsConfig = Field(default_factory=ModelsConfig, description="模型配置")
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig, description="渠道配置")
    agents: AgentsConfig = Field(default_factory=AgentsConfig, description="代理配置")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="日志配置")
    plugins: dict[str, Any] = Field(default_factory=dict, description="插件配置")
    custom: dict[str, Any] = Field(default_factory=dict, description="自定义配置")

    model_config = {"use_enum_values": True}
