"""配置类型定义。

本模块定义了 TigerClaw 中使用的配置相关类型，
包括网关配置、模型配置、渠道配置等。
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


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
    """速率限制配置。"""

    max_attempts: int = Field(default=10, description="最大尝试次数")
    window_ms: int = Field(default=60000, description="滑动窗口时间（毫秒）")
    lockout_ms: int = Field(default=300000, description="锁定时间（毫秒）")
    exempt_loopback: bool = Field(default=True, description="是否豁免回环地址")


class AuthConfig(BaseModel):
    """认证配置。"""

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


class GatewayConfig(BaseModel):
    """Gateway 配置。"""

    bind: BindMode = Field(default=BindMode.LOOPBACK, description="绑定模式")
    host: str | None = Field(None, description="绑定地址")
    port: int = Field(default=18789, ge=1, le=65535, description="端口号")
    auth: AuthConfig = Field(default_factory=AuthConfig, description="认证配置")
    trusted_proxies: list[str] = Field(default_factory=list, description="受信任的代理地址列表")
    control_ui_enabled: bool = Field(default=True, description="是否启用控制UI")
    openai_chat_completions_enabled: bool = Field(default=True, description="是否启用OpenAI兼容API")
    cors_origins: list[str] = Field(default_factory=lambda: ["*"], description="CORS允许的源")
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


class ModelsConfig(BaseModel):
    """模型配置集合。"""

    default: str = Field(default="gpt-4", description="默认模型")
    models: list[ModelConfig] = Field(default_factory=list, description="模型列表")


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


class AgentsConfig(BaseModel):
    """代理配置集合。"""

    main: AgentConfig = Field(default_factory=AgentConfig, description="主代理配置")
    subagents: dict[str, AgentConfig] = Field(default_factory=dict, description="子代理配置")


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
