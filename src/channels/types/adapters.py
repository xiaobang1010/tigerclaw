"""
渠道适配器协议定义。

定义渠道插件与核心系统之间的适配器协议接口。
这些协议定义了渠道插件需要实现的可选接口。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .core import (
    ChannelAccountSnapshot,
    ChannelAccountState,
    ChannelDirectoryEntry,
    ChannelSetupInput,
    ChannelStatusIssue,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from channels.actions import (
        AgentToolResult,
        ChannelMessageActionContext,
        ChannelMessageActionDiscoveryContext,
        ChannelMessageActionName,
        ChannelMessageToolDiscovery,
        ChannelThreadingToolContext,
        ChannelToolSend,
    )


@runtime_checkable
class ChannelConfigAdapter(Protocol):
    """
    配置适配器协议。

    定义渠道配置管理的核心接口，包括账户列表、解析、启用/禁用等。
    """

    def list_account_ids(self, cfg: Any) -> list[str]:
        """
        列出配置中的所有账户 ID。

        Args:
            cfg: 应用配置对象

        Returns:
            账户 ID 列表
        """
        ...

    def resolve_account(self, cfg: Any, account_id: str | None) -> Any:
        """
        解析账户对象。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID，如果为 None 则使用默认账户

        Returns:
            解析后的账户对象
        """
        ...

    def inspect_account(self, cfg: Any, account_id: str | None) -> Any:
        """
        检查账户信息。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID

        Returns:
            账户检查结果
        """
        ...

    def default_account_id(self, cfg: Any) -> str:
        """
        获取默认账户 ID。

        Args:
            cfg: 应用配置对象

        Returns:
            默认账户 ID
        """
        ...

    def set_account_enabled(
        self, cfg: Any, account_id: str, enabled: bool
    ) -> Any:
        """
        设置账户启用状态。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            enabled: 是否启用

        Returns:
            更新后的配置对象
        """
        ...

    def delete_account(self, cfg: Any, account_id: str) -> Any:
        """
        删除账户。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID

        Returns:
            更新后的配置对象
        """
        ...

    def is_enabled(self, account: Any, cfg: Any) -> bool:
        """
        检查账户是否启用。

        Args:
            account: 账户对象
            cfg: 应用配置对象

        Returns:
            是否启用
        """
        ...

    def disabled_reason(self, account: Any, cfg: Any) -> str:
        """
        获取禁用原因。

        Args:
            account: 账户对象
            cfg: 应用配置对象

        Returns:
            禁用原因描述
        """
        ...

    async def is_configured(self, account: Any, cfg: Any) -> bool:
        """
        检查账户是否已配置。

        Args:
            account: 账户对象
            cfg: 应用配置对象

        Returns:
            是否已配置
        """
        ...

    def unconfigured_reason(self, account: Any, cfg: Any) -> str:
        """
        获取未配置原因。

        Args:
            account: 账户对象
            cfg: 应用配置对象

        Returns:
            未配置原因描述
        """
        ...

    def describe_account(self, account: Any, cfg: Any) -> ChannelAccountSnapshot:
        """
        描述账户状态。

        Args:
            account: 账户对象
            cfg: 应用配置对象

        Returns:
            账户快照
        """
        ...

    def resolve_allow_from(
        self, cfg: Any, account_id: str | None
    ) -> Sequence[str | int] | None:
        """
        解析允许来源列表。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID

        Returns:
            允许来源列表
        """
        ...

    def format_allow_from(
        self, cfg: Any, account_id: str | None, allow_from: Sequence[str | int]
    ) -> list[str]:
        """
        格式化允许来源列表。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            allow_from: 允许来源列表

        Returns:
            格式化后的允许来源列表
        """
        ...

    def resolve_default_to(self, cfg: Any, account_id: str | None) -> str | None:
        """
        解析默认目标。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID

        Returns:
            默认目标
        """
        ...


@runtime_checkable
class ChannelSecurityAdapter(Protocol):
    """
    安全适配器协议。

    定义渠道安全相关的接口，包括私聊策略和安全警告收集。
    """

    def resolve_dm_policy(self, cfg: Any, account: Any) -> dict[str, Any] | None:
        """
        解析私聊策略。

        Args:
            cfg: 应用配置对象
            account: 账户对象

        Returns:
            私聊策略配置
        """
        ...

    async def collect_warnings(self, cfg: Any, account: Any) -> list[str]:
        """
        收集安全警告。

        Args:
            cfg: 应用配置对象
            account: 账户对象

        Returns:
            警告消息列表
        """
        ...


@runtime_checkable
class ChannelOutboundAdapter(Protocol):
    """
    出站适配器协议。

    定义消息发送相关的接口，包括文本分块、目标解析、消息发送等。
    """

    @property
    def delivery_mode(self) -> str:
        """
        获取投递模式。

        Returns:
            投递模式：direct/gateway/hybrid
        """
        ...

    def chunker(self, text: str, limit: int) -> list[str]:
        """
        文本分块器。

        Args:
            text: 待分块文本
            limit: 每块字符限制

        Returns:
            分块后的文本列表
        """
        ...

    @property
    def text_chunk_limit(self) -> int | None:
        """
        获取文本分块限制。

        Returns:
            字符限制数
        """
        ...

    @property
    def poll_max_options(self) -> int | None:
        """
        获取投票选项最大数。

        Returns:
            最大选项数
        """
        ...

    def normalize_payload(self, payload: Any) -> Any | None:
        """
        标准化消息负载。

        Args:
            payload: 原始负载

        Returns:
            标准化后的负载
        """
        ...

    def resolve_target(
        self,
        cfg: Any,
        to: str | None,
        allow_from: list[str],
        account_id: str | None,
        mode: str,
    ) -> dict[str, Any]:
        """
        解析发送目标。

        Args:
            cfg: 应用配置对象
            to: 目标地址
            allow_from: 允许来源列表
            account_id: 账户 ID
            mode: 解析模式

        Returns:
            解析结果，包含 ok 和 to 或 error
        """
        ...

    async def send_text(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """
        发送文本消息。

        Args:
            ctx: 发送上下文

        Returns:
            发送结果
        """
        ...

    async def send_media(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """
        发送媒体消息。

        Args:
            ctx: 发送上下文

        Returns:
            发送结果
        """
        ...

    async def send_poll(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """
        发送投票。

        Args:
            ctx: 发送上下文

        Returns:
            发送结果
        """
        ...


@runtime_checkable
class ChannelStatusAdapter(Protocol):
    """
    状态适配器协议。

    定义渠道状态监控相关的接口，包括探测、审计、快照构建等。
    """

    @property
    def default_runtime(self) -> ChannelAccountSnapshot | None:
        """
        获取默认运行时状态。

        Returns:
            默认账户快照
        """
        ...

    async def build_channel_summary(
        self,
        account: Any,
        cfg: Any,
        default_account_id: str,
        snapshot: ChannelAccountSnapshot,
    ) -> dict[str, Any]:
        """
        构建渠道摘要。

        Args:
            account: 账户对象
            cfg: 应用配置对象
            default_account_id: 默认账户 ID
            snapshot: 账户快照

        Returns:
            渠道摘要
        """
        ...

    async def probe_account(
        self, account: Any, timeout_ms: int, cfg: Any
    ) -> Any:
        """
        探测账户状态。

        Args:
            account: 账户对象
            timeout_ms: 超时时间（毫秒）
            cfg: 应用配置对象

        Returns:
            探测结果
        """
        ...

    def format_capabilities_probe(self, probe: Any) -> list[dict[str, Any]]:
        """
        格式化能力探测结果。

        Args:
            probe: 探测结果

        Returns:
            格式化后的能力显示行
        """
        ...

    async def audit_account(
        self, account: Any, timeout_ms: int, cfg: Any, probe: Any | None
    ) -> Any:
        """
        审计账户。

        Args:
            account: 账户对象
            timeout_ms: 超时时间（毫秒）
            cfg: 应用配置对象
            probe: 探测结果

        Returns:
            审计结果
        """
        ...

    async def build_capabilities_diagnostics(
        self,
        account: Any,
        timeout_ms: int,
        cfg: Any,
        probe: Any | None,
        audit: Any | None,
        target: str | None,
    ) -> dict[str, Any] | None:
        """
        构建能力诊断信息。

        Args:
            account: 账户对象
            timeout_ms: 超时时间（毫秒）
            cfg: 应用配置对象
            probe: 探测结果
            audit: 审计结果
            target: 目标地址

        Returns:
            能力诊断信息
        """
        ...

    async def build_account_snapshot(
        self,
        account: Any,
        cfg: Any,
        runtime: ChannelAccountSnapshot | None,
        probe: Any | None,
        audit: Any | None,
    ) -> ChannelAccountSnapshot:
        """
        构建账户快照。

        Args:
            account: 账户对象
            cfg: 应用配置对象
            runtime: 运行时状态
            probe: 探测结果
            audit: 审计结果

        Returns:
            账户快照
        """
        ...

    def log_self_id(
        self,
        account: Any,
        cfg: Any,
        runtime: Any,
        include_channel_prefix: bool,
    ) -> None:
        """
        记录自身 ID。

        Args:
            account: 账户对象
            cfg: 应用配置对象
            runtime: 运行时环境
            include_channel_prefix: 是否包含渠道前缀
        """
        ...

    def resolve_account_state(
        self,
        account: Any,
        cfg: Any,
        configured: bool,
        enabled: bool,
    ) -> ChannelAccountState:
        """
        解析账户状态。

        Args:
            account: 账户对象
            cfg: 应用配置对象
            configured: 是否已配置
            enabled: 是否启用

        Returns:
            账户状态
        """
        ...

    def collect_status_issues(
        self, accounts: list[ChannelAccountSnapshot]
    ) -> list[ChannelStatusIssue]:
        """
        收集状态问题。

        Args:
            accounts: 账户快照列表

        Returns:
            状态问题列表
        """
        ...


@runtime_checkable
class ChannelPairingAdapter(Protocol):
    """
    配对适配器协议。

    定义渠道配对相关的接口，包括 ID 标签、条目标准化、审批通知等。
    """

    @property
    def id_label(self) -> str:
        """
        获取 ID 标签。

        Returns:
            ID 标签（如 "手机号"、"邮箱"）
        """
        ...

    def normalize_allow_entry(self, entry: str) -> str:
        """
        标准化允许条目。

        Args:
            entry: 原始条目

        Returns:
            标准化后的条目
        """
        ...

    async def notify_approval(
        self,
        cfg: Any,
        id: str,
        account_id: str | None,
        runtime: Any | None,
    ) -> None:
        """
        发送审批通知。

        Args:
            cfg: 应用配置对象
            id: 审批 ID
            account_id: 账户 ID
            runtime: 运行时环境
        """
        ...


@runtime_checkable
class ChannelMessageActionAdapter(Protocol):
    """
    消息动作适配器协议。

    定义消息工具动作相关的接口，包括动作发现、支持检查、执行处理等。
    """

    def describe_message_tool(
        self,
        params: ChannelMessageActionDiscoveryContext,
    ) -> ChannelMessageToolDiscovery | None:
        """
        描述消息工具。

        统一的消息工具发现接口，返回该渠道支持的动作、能力和模式片段。

        Args:
            params: 发现上下文，包含路由/账户范围信息

        Returns:
            工具描述，包含 actions、capabilities、schema
        """
        ...

    def supports_action(self, params: ChannelMessageActionName) -> bool:
        """
        检查是否支持指定动作。

        Args:
            params: 动作名称

        Returns:
            是否支持
        """
        ...

    def requires_trusted_requester_sender(
        self,
        params: ChannelMessageActionName,
        tool_context: ChannelThreadingToolContext | None,
    ) -> bool:
        """
        检查是否需要可信的请求发送者。

        Args:
            params: 动作名称
            tool_context: 工具上下文

        Returns:
            是否需要
        """
        ...

    def extract_tool_send(self, params: dict[str, Any]) -> ChannelToolSend | None:
        """
        提取工具发送参数。

        Args:
            params: 工具参数

        Returns:
            发送参数
        """
        ...

    async def handle_action(self, ctx: ChannelMessageActionContext) -> AgentToolResult:
        """
        处理动作执行。

        Args:
            ctx: 动作上下文

        Returns:
            执行结果
        """
        ...


@runtime_checkable
class ChannelDirectoryAdapter(Protocol):
    """
    目录适配器协议。

    定义渠道目录相关的接口，包括自身信息、用户列表、群组列表等。
    """

    async def self(
        self, cfg: Any, account_id: str | None, runtime: Any
    ) -> ChannelDirectoryEntry | None:
        """
        获取当前用户信息。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            runtime: 运行时环境

        Returns:
            当前用户条目
        """
        ...

    async def list_peers(
        self,
        cfg: Any,
        account_id: str | None,
        query: str | None,
        limit: int | None,
        runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        列出用户/同伴。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            query: 搜索查询
            limit: 结果限制
            runtime: 运行时环境

        Returns:
            用户条目列表
        """
        ...

    async def list_peers_live(
        self,
        cfg: Any,
        account_id: str | None,
        query: str | None,
        limit: int | None,
        runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        实时列出用户/同伴。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            query: 搜索查询
            limit: 结果限制
            runtime: 运行时环境

        Returns:
            用户条目列表
        """
        ...

    async def list_groups(
        self,
        cfg: Any,
        account_id: str | None,
        query: str | None,
        limit: int | None,
        runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        列出群组。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            query: 搜索查询
            limit: 结果限制
            runtime: 运行时环境

        Returns:
            群组条目列表
        """
        ...

    async def list_groups_live(
        self,
        cfg: Any,
        account_id: str | None,
        query: str | None,
        limit: int | None,
        runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        实时列出群组。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            query: 搜索查询
            limit: 结果限制
            runtime: 运行时环境

        Returns:
            群组条目列表
        """
        ...

    async def list_group_members(
        self,
        cfg: Any,
        account_id: str | None,
        group_id: str,
        limit: int | None,
        runtime: Any,
    ) -> list[ChannelDirectoryEntry]:
        """
        列出群组成员。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            group_id: 群组 ID
            limit: 结果限制
            runtime: 运行时环境

        Returns:
            成员条目列表
        """
        ...


@runtime_checkable
class ChannelLifecycleAdapter(Protocol):
    """
    生命周期适配器协议。

    定义渠道生命周期相关的接口，包括配置变更和账户移除回调。
    """

    async def on_account_config_changed(
        self,
        prev_cfg: Any,
        next_cfg: Any,
        account_id: str,
        runtime: Any,
    ) -> None:
        """
        账户配置变更回调。

        Args:
            prev_cfg: 变更前配置
            next_cfg: 变更后配置
            account_id: 账户 ID
            runtime: 运行时环境
        """
        ...

    async def on_account_removed(
        self,
        prev_cfg: Any,
        account_id: str,
        runtime: Any,
    ) -> None:
        """
        账户移除回调。

        Args:
            prev_cfg: 移除前配置
            account_id: 账户 ID
            runtime: 运行时环境
        """
        ...


@runtime_checkable
class ChannelSetupAdapter(Protocol):
    """
    设置适配器协议。

    定义渠道设置相关的接口，包括账户 ID 解析、配置应用、输入验证等。
    """

    def resolve_account_id(
        self, cfg: Any, account_id: str | None, input: ChannelSetupInput | None
    ) -> str:
        """
        解析账户 ID。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            input: 设置输入

        Returns:
            解析后的账户 ID
        """
        ...

    def resolve_binding_account_id(
        self, cfg: Any, agent_id: str, account_id: str | None
    ) -> str | None:
        """
        解析绑定账户 ID。

        Args:
            cfg: 应用配置对象
            agent_id: 代理 ID
            account_id: 账户 ID

        Returns:
            解析后的账户 ID
        """
        ...

    def apply_account_name(
        self, cfg: Any, account_id: str, name: str | None
    ) -> Any:
        """
        应用账户名称。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            name: 账户名称

        Returns:
            更新后的配置对象
        """
        ...

    def apply_account_config(
        self, cfg: Any, account_id: str, input: ChannelSetupInput
    ) -> Any:
        """
        应用账户配置。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            input: 设置输入

        Returns:
            更新后的配置对象
        """
        ...

    async def after_account_config_written(
        self,
        previous_cfg: Any,
        cfg: Any,
        account_id: str,
        input: ChannelSetupInput,
        runtime: Any,
    ) -> None:
        """
        配置写入后回调。

        Args:
            previous_cfg: 写入前配置
            cfg: 写入后配置
            account_id: 账户 ID
            input: 设置输入
            runtime: 运行时环境
        """
        ...

    def validate_input(
        self, cfg: Any, account_id: str, input: ChannelSetupInput
    ) -> str | None:
        """
        验证输入。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            input: 设置输入

        Returns:
            验证错误消息，None 表示验证通过
        """
        ...


@runtime_checkable
class ChannelGatewayAdapter(Protocol):
    """
    网关适配器协议。

    定义渠道网关相关的接口，包括账户启停、登录登出等。
    """

    async def start_account(self, ctx: dict[str, Any]) -> Any:
        """
        启动账户。

        Args:
            ctx: 网关上下文

        Returns:
            启动结果
        """
        ...

    async def stop_account(self, ctx: dict[str, Any]) -> None:
        """
        停止账户。

        Args:
            ctx: 网关上下文
        """
        ...

    async def login_with_qr_start(
        self,
        account_id: str | None,
        force: bool,
        timeout_ms: int | None,
        verbose: bool,
    ) -> dict[str, Any]:
        """
        开始二维码登录。

        Args:
            account_id: 账户 ID
            force: 是否强制重新登录
            timeout_ms: 超时时间（毫秒）
            verbose: 是否详细输出

        Returns:
            包含 qr_data_url 和 message 的结果
        """
        ...

    async def login_with_qr_wait(
        self, account_id: str | None, timeout_ms: int | None
    ) -> dict[str, Any]:
        """
        等待二维码登录完成。

        Args:
            account_id: 账户 ID
            timeout_ms: 超时时间（毫秒）

        Returns:
            包含 connected 和 message 的结果
        """
        ...

    async def logout_account(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """
        登出账户。

        Args:
            ctx: 登出上下文

        Returns:
            登出结果
        """
        ...


@runtime_checkable
class ChannelHeartbeatAdapter(Protocol):
    """
    心跳适配器协议。

    定义渠道心跳相关的接口，包括就绪检查和收件人解析。
    """

    async def check_ready(
        self, cfg: Any, account_id: str | None, deps: dict[str, Any] | None
    ) -> dict[str, Any]:
        """
        检查就绪状态。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            deps: 依赖项

        Returns:
            包含 ok 和 reason 的结果
        """
        ...

    def resolve_recipients(
        self, cfg: Any, opts: dict[str, Any] | None
    ) -> dict[str, Any]:
        """
        解析收件人。

        Args:
            cfg: 应用配置对象
            opts: 选项，包含 to 和 all

        Returns:
            包含 recipients 和 source 的结果
        """
        ...


@runtime_checkable
class ChannelResolverAdapter(Protocol):
    """
    解析器适配器协议。

    定义目标解析相关的接口。
    """

    async def resolve_targets(
        self,
        cfg: Any,
        account_id: str | None,
        inputs: list[str],
        kind: str,
        runtime: Any,
    ) -> list[dict[str, Any]]:
        """
        解析目标。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            inputs: 输入列表
            kind: 解析类型（user/group）
            runtime: 运行时环境

        Returns:
            解析结果列表
        """
        ...


@runtime_checkable
class ChannelGroupAdapter(Protocol):
    """
    群组适配器协议。

    定义群组相关策略的接口。
    """

    def resolve_require_mention(self, ctx: dict[str, Any]) -> bool | None:
        """
        解析是否需要提及。

        Args:
            ctx: 群组上下文

        Returns:
            是否需要提及
        """
        ...

    def resolve_group_intro_hint(self, ctx: dict[str, Any]) -> str | None:
        """
        解析群组介绍提示。

        Args:
            ctx: 群组上下文

        Returns:
            介绍提示
        """
        ...

    def resolve_tool_policy(self, ctx: dict[str, Any]) -> Any | None:
        """
        解析工具策略。

        Args:
            ctx: 群组上下文

        Returns:
            工具策略配置
        """
        ...


@runtime_checkable
class ChannelAuthAdapter(Protocol):
    """
    认证适配器协议。

    定义渠道认证相关的接口。
    """

    async def login(
        self,
        cfg: Any,
        account_id: str | None,
        runtime: Any,
        verbose: bool,
        channel_input: str | None,
    ) -> None:
        """
        执行登录。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            runtime: 运行时环境
            verbose: 是否详细输出
            channel_input: 渠道输入
        """
        ...


@runtime_checkable
class ChannelAllowlistAdapter(Protocol):
    """
    白名单适配器协议。

    定义渠道白名单管理相关的接口。
    """

    def apply_config_edit(
        self,
        cfg: Any,
        parsed_config: dict[str, Any],
        account_id: str | None,
        scope: str,
        action: str,
        entry: str,
    ) -> dict[str, Any] | None:
        """
        应用配置编辑。

        Args:
            cfg: 应用配置对象
            parsed_config: 解析后的配置
            account_id: 账户 ID
            scope: 作用域（dm/group）
            action: 操作（add/remove）
            entry: 条目

        Returns:
            编辑结果
        """
        ...

    async def read_config(
        self, cfg: Any, account_id: str | None
    ) -> dict[str, Any]:
        """
        读取配置。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID

        Returns:
            配置内容
        """
        ...

    async def resolve_names(
        self,
        cfg: Any,
        account_id: str | None,
        scope: str,
        entries: list[str],
    ) -> list[dict[str, Any]]:
        """
        解析名称。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            scope: 作用域
            entries: 条目列表

        Returns:
            解析结果列表
        """
        ...

    def supports_scope(self, scope: str) -> bool:
        """
        检查是否支持指定作用域。

        Args:
            scope: 作用域（dm/group/all）

        Returns:
            是否支持
        """
        ...


@runtime_checkable
class ChannelThreadingAdapter(Protocol):
    """
    线程适配器协议。

    定义渠道线程/话题相关的接口。
    """

    def resolve_reply_to_mode(
        self, cfg: Any, account_id: str | None, chat_type: str | None
    ) -> str:
        """
        解析回复模式。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            chat_type: 聊天类型

        Returns:
            回复模式（off/first/all）
        """
        ...

    def build_tool_context(
        self, cfg: Any, account_id: str | None, context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        构建工具上下文。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            context: 线程上下文

        Returns:
            工具上下文
        """
        ...

    def resolve_auto_thread_id(
        self,
        cfg: Any,
        account_id: str | None,
        to: str,
        tool_context: dict[str, Any] | None,
        reply_to_id: str | None,
    ) -> str | None:
        """
        解析自动线程 ID。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            to: 目标地址
            tool_context: 工具上下文
            reply_to_id: 回复 ID

        Returns:
            线程 ID
        """
        ...

    def resolve_reply_transport(
        self,
        cfg: Any,
        account_id: str | None,
        thread_id: str | int | None,
        reply_to_id: str | None,
    ) -> dict[str, Any] | None:
        """
        解析回复传输。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            thread_id: 线程 ID
            reply_to_id: 回复 ID

        Returns:
            回复传输信息
        """
        ...


@runtime_checkable
class ChannelMessagingAdapter(Protocol):
    """
    消息适配器协议。

    定义渠道消息处理相关的接口。
    """

    def normalize_target(self, raw: str) -> str | None:
        """
        标准化目标。

        Args:
            raw: 原始目标字符串

        Returns:
            标准化后的目标
        """
        ...

    def parse_explicit_target(self, raw: str) -> dict[str, Any] | None:
        """
        解析显式目标。

        Args:
            raw: 原始目标字符串

        Returns:
            解析结果，包含 to、threadId、chatType
        """
        ...

    def infer_target_chat_type(self, to: str) -> str | None:
        """
        推断目标聊天类型。

        Args:
            to: 目标地址

        Returns:
            聊天类型
        """
        ...

    def format_target_display(
        self, target: str, display: str | None, kind: str | None
    ) -> str:
        """
        格式化目标显示。

        Args:
            target: 目标地址
            display: 显示名称
            kind: 条目类型

        Returns:
            格式化后的显示字符串
        """
        ...


@runtime_checkable
class ChannelExecApprovalAdapter(Protocol):
    """
    执行审批适配器协议。

    定义执行审批相关的接口，用于处理需要审批的操作流程。
    参考 OpenClaw 实现：src/channels/plugins/types.adapters.ts
    """

    def get_initiating_surface_state(
        self, cfg: Any, account_id: str | None
    ) -> str:
        """
        获取发起表面状态。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID

        Returns:
            状态：enabled/disabled/unsupported
        """
        ...

    def should_suppress_local_prompt(
        self, cfg: Any, account_id: str | None, payload: Any
    ) -> bool:
        """
        是否抑制本地提示。

        Args:
            cfg: 应用配置对象
            account_id: 账户 ID
            payload: 消息负载

        Returns:
            是否抑制
        """
        ...

    def has_configured_dm_route(self, cfg: Any) -> bool:
        """
        是否有已配置的 DM 路由。

        Args:
            cfg: 应用配置对象

        Returns:
            是否有已配置的 DM 路由
        """
        ...

    def should_suppress_forwarding_fallback(
        self, cfg: Any, target: dict[str, Any], request: dict[str, Any]
    ) -> bool:
        """
        是否抑制转发后备。

        Args:
            cfg: 应用配置对象
            target: 转发目标
            request: 审批请求

        Returns:
            是否抑制
        """
        ...

    def build_pending_payload(
        self,
        cfg: Any,
        request: dict[str, Any],
        target: dict[str, Any],
        now_ms: float,
    ) -> Any | None:
        """
        构建待审批负载。

        Args:
            cfg: 应用配置对象
            request: 审批请求
            target: 转发目标
            now_ms: 当前时间戳（毫秒）

        Returns:
            消息负载
        """
        ...

    def build_resolved_payload(
        self, cfg: Any, resolved: dict[str, Any], target: dict[str, Any]
    ) -> Any | None:
        """
        构建已解决负载。

        Args:
            cfg: 应用配置对象
            resolved: 已解决状态
            target: 转发目标

        Returns:
            消息负载
        """
        ...

    async def before_deliver_pending(
        self, cfg: Any, target: dict[str, Any], payload: Any
    ) -> None:
        """
        交付待审批负载前回调。

        Args:
            cfg: 应用配置对象
            target: 转发目标
            payload: 消息负载
        """
        ...


@runtime_checkable
class ChannelCommandAdapter(Protocol):
    """
    原生命令适配器协议。

    定义渠道原生命令相关的配置接口。
    参考 OpenClaw 实现：src/channels/plugins/types.adapters.ts
    """

    @property
    def enforce_owner_for_commands(self) -> bool:
        """
        是否强制只有所有者可以执行命令。

        Returns:
            是否强制所有者执行
        """
        ...

    @property
    def skip_when_config_empty(self) -> bool:
        """
        当配置为空时是否跳过命令处理。

        Returns:
            是否跳过
        """
        ...


@runtime_checkable
class ChannelMentionAdapter(Protocol):
    """
    提及处理适配器协议。

    定义渠道提及相关的接口，用于处理消息中的 @提及。
    参考 OpenClaw 实现：src/channels/plugins/types.core.ts
    """

    def strip_regexes(
        self, ctx: Any, cfg: Any | None, agent_id: str | None
    ) -> list[Any]:
        """
        获取提及剥离正则表达式列表。

        Args:
            ctx: 消息上下文
            cfg: 配置对象
            agent_id: 代理 ID

        Returns:
            正则表达式列表
        """
        ...

    def strip_patterns(
        self, ctx: Any, cfg: Any | None, agent_id: str | None
    ) -> list[str]:
        """
        获取提及剥离模式列表。

        Args:
            ctx: 消息上下文
            cfg: 配置对象
            agent_id: 代理 ID

        Returns:
            字符串模式列表
        """
        ...

    def strip_mentions(
        self, text: str, ctx: Any, cfg: Any | None, agent_id: str | None
    ) -> str:
        """
        剥离提及。

        Args:
            text: 待处理文本
            ctx: 消息上下文
            cfg: 配置对象
            agent_id: 代理 ID

        Returns:
            清理后的文本
        """
        ...


@runtime_checkable
class ChannelStreamingAdapter(Protocol):
    """
    流式传输适配器协议。

    定义渠道流式传输相关的配置接口。
    参考 OpenClaw 实现：src/channels/plugins/types.core.ts
    """

    @property
    def block_streaming_coalesce_defaults(self) -> dict[str, Any] | None:
        """
        获取流式传输合并默认配置。

        Returns:
            包含 min_chars 和 idle_ms 的配置字典
        """
        ...
