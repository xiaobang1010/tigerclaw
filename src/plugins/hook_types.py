"""插件 Hook 类型定义。

参考 OpenClaw 的 Hook 系统设计，支持多种生命周期钩子。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PluginHookName(StrEnum):
    """Hook 名称枚举。"""

    BEFORE_MODEL_RESOLVE = "before_model_resolve"
    BEFORE_PROMPT_BUILD = "before_prompt_build"
    BEFORE_AGENT_START = "before_agent_start"
    LLM_INPUT = "llm_input"
    LLM_OUTPUT = "llm_output"
    AGENT_END = "agent_end"
    BEFORE_COMPACTION = "before_compaction"
    AFTER_COMPACTION = "after_compaction"
    BEFORE_RESET = "before_reset"
    INBOUND_CLAIM = "inbound_claim"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENDING = "message_sending"
    MESSAGE_SENT = "message_sent"
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    TOOL_RESULT_PERSIST = "tool_result_persist"
    BEFORE_MESSAGE_WRITE = "before_message_write"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SUBAGENT_SPAWNING = "subagent_spawning"
    SUBAGENT_DELIVERY_TARGET = "subagent_delivery_target"
    SUBAGENT_SPAWNED = "subagent_spawned"
    SUBAGENT_ENDED = "subagent_ended"
    GATEWAY_START = "gateway_start"
    GATEWAY_STOP = "gateway_stop"
    BEFORE_DISPATCH = "before_dispatch"


PLUGIN_HOOK_NAMES = [
    "before_model_resolve",
    "before_prompt_build",
    "before_agent_start",
    "llm_input",
    "llm_output",
    "agent_end",
    "before_compaction",
    "after_compaction",
    "before_reset",
    "inbound_claim",
    "message_received",
    "message_sending",
    "message_sent",
    "before_tool_call",
    "after_tool_call",
    "tool_result_persist",
    "before_message_write",
    "session_start",
    "session_end",
    "subagent_spawning",
    "subagent_delivery_target",
    "subagent_spawned",
    "subagent_ended",
    "gateway_start",
    "gateway_stop",
    "before_dispatch",
]


@dataclass
class PluginHookAgentContext:
    """Agent Hook 上下文。"""

    agent_id: str | None = None
    session_key: str | None = None
    session_id: str | None = None
    workspace_dir: str | None = None
    message_provider: str | None = None
    trigger: str | None = None
    channel_id: str | None = None


@dataclass
class PluginHookBeforeModelResolveEvent:
    """before_model_resolve Hook 事件。"""

    prompt: str = ""


@dataclass
class PluginHookBeforeModelResolveResult:
    """before_model_resolve Hook 结果。"""

    model_override: str | None = None
    provider_override: str | None = None


@dataclass
class PluginHookBeforePromptBuildEvent:
    """before_prompt_build Hook 事件。"""

    prompt: str = ""
    messages: list[Any] = field(default_factory=list)


@dataclass
class PluginHookBeforePromptBuildResult:
    """before_prompt_build Hook 结果。"""

    system_prompt: str | None = None
    prepend_context: str | None = None
    prepend_system_context: str | None = None
    append_system_context: str | None = None


PLUGIN_PROMPT_MUTATION_RESULT_FIELDS = [
    "systemPrompt",
    "prependContext",
    "prependSystemContext",
    "appendSystemContext",
]


@dataclass
class PluginHookBeforeAgentStartEvent:
    """before_agent_start Hook 事件。"""

    prompt: str = ""
    messages: list[Any] | None = None


@dataclass
class PluginHookBeforeAgentStartResult:
    """before_agent_start Hook 结果。"""

    model_override: str | None = None
    provider_override: str | None = None
    system_prompt: str | None = None
    prepend_context: str | None = None
    prepend_system_context: str | None = None
    append_system_context: str | None = None


@dataclass
class PluginHookLlmInputEvent:
    """llm_input Hook 事件。"""

    run_id: str = ""
    session_id: str = ""
    provider: str = ""
    model: str = ""
    system_prompt: str | None = None
    prompt: str = ""
    history_messages: list[Any] = field(default_factory=list)
    images_count: int = 0


@dataclass
class PluginHookLlmOutputEvent:
    """llm_output Hook 事件。"""

    run_id: str = ""
    session_id: str = ""
    provider: str = ""
    model: str = ""
    assistant_texts: list[str] = field(default_factory=list)
    last_assistant: Any = None
    usage: dict[str, int] | None = None


@dataclass
class PluginHookAgentEndEvent:
    """agent_end Hook 事件。"""

    messages: list[Any] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    duration_ms: int | None = None


@dataclass
class PluginHookBeforeCompactionEvent:
    """before_compaction Hook 事件。"""

    message_count: int = 0
    compacting_count: int | None = None
    token_count: int | None = None
    messages: list[Any] | None = None
    session_file: str | None = None


@dataclass
class PluginHookAfterCompactionEvent:
    """after_compaction Hook 事件。"""

    message_count: int = 0
    token_count: int | None = None
    compacted_count: int = 0
    session_file: str | None = None


@dataclass
class PluginHookBeforeResetEvent:
    """before_reset Hook 事件。"""

    session_file: str | None = None
    messages: list[Any] | None = None
    reason: str | None = None


@dataclass
class PluginHookMessageContext:
    """消息上下文。"""

    channel_id: str = ""
    account_id: str | None = None
    conversation_id: str | None = None


@dataclass
class PluginHookInboundClaimContext(PluginHookMessageContext):
    """inbound_claim Hook 上下文。"""

    parent_conversation_id: str | None = None
    sender_id: str | None = None
    message_id: str | None = None


@dataclass
class PluginHookInboundClaimEvent:
    """inbound_claim Hook 事件。"""

    content: str = ""
    body: str | None = None
    body_for_agent: str | None = None
    transcript: str | None = None
    timestamp: float | None = None
    channel: str = ""
    account_id: str | None = None
    conversation_id: str | None = None
    parent_conversation_id: str | None = None
    sender_id: str | None = None
    sender_name: str | None = None
    sender_username: str | None = None
    thread_id: str | int | None = None
    message_id: str | None = None
    is_group: bool = False
    command_authorized: bool | None = None
    was_mentioned: bool | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class PluginHookInboundClaimResult:
    """inbound_claim Hook 结果。"""

    handled: bool = False


@dataclass
class PluginHookBeforeDispatchEvent:
    """before_dispatch Hook 事件。"""

    content: str = ""
    body: str | None = None
    channel: str | None = None
    session_key: str | None = None
    sender_id: str | None = None
    is_group: bool | None = None
    timestamp: float | None = None


@dataclass
class PluginHookBeforeDispatchContext:
    """before_dispatch Hook 上下文。"""

    channel_id: str | None = None
    account_id: str | None = None
    conversation_id: str | None = None
    session_key: str | None = None
    sender_id: str | None = None


@dataclass
class PluginHookBeforeDispatchResult:
    """before_dispatch Hook 结果。"""

    handled: bool = False
    text: str | None = None


@dataclass
class PluginHookMessageReceivedEvent:
    """message_received Hook 事件。"""

    from_id: str = ""
    content: str = ""
    timestamp: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class PluginHookMessageSendingEvent:
    """message_sending Hook 事件。"""

    to_id: str = ""
    content: str = ""
    metadata: dict[str, Any] | None = None


@dataclass
class PluginHookMessageSendingResult:
    """message_sending Hook 结果。"""

    content: str | None = None
    cancel: bool = False


@dataclass
class PluginHookMessageSentEvent:
    """message_sent Hook 事件。"""

    to_id: str = ""
    content: str = ""
    success: bool = True
    error: str | None = None


@dataclass
class PluginHookToolContext:
    """工具上下文。"""

    agent_id: str | None = None
    session_key: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    tool_name: str = ""
    tool_call_id: str | None = None


@dataclass
class PluginHookBeforeToolCallEvent:
    """before_tool_call Hook 事件。"""

    tool_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    tool_call_id: str | None = None


@dataclass
class PluginHookBeforeToolCallResult:
    """before_tool_call Hook 结果。"""

    params: dict[str, Any] | None = None
    block: bool = False
    block_reason: str | None = None


@dataclass
class PluginHookAfterToolCallEvent:
    """after_tool_call Hook 事件。"""

    tool_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    tool_call_id: str | None = None
    result: Any = None
    error: str | None = None
    duration_ms: int | None = None


@dataclass
class PluginHookToolResultPersistContext:
    """tool_result_persist Hook 上下文。"""

    agent_id: str | None = None
    session_key: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None


@dataclass
class PluginHookToolResultPersistEvent:
    """tool_result_persist Hook 事件。"""

    tool_name: str | None = None
    tool_call_id: str | None = None
    message: Any = None
    is_synthetic: bool = False


@dataclass
class PluginHookToolResultPersistResult:
    """tool_result_persist Hook 结果。"""

    message: Any = None


@dataclass
class PluginHookBeforeMessageWriteEvent:
    """before_message_write Hook 事件。"""

    message: Any = None
    session_key: str | None = None
    agent_id: str | None = None


@dataclass
class PluginHookBeforeMessageWriteResult:
    """before_message_write Hook 结果。"""

    block: bool = False
    message: Any = None


@dataclass
class PluginHookSessionContext:
    """Session 上下文。"""

    agent_id: str | None = None
    session_id: str = ""
    session_key: str | None = None


@dataclass
class PluginHookSessionStartEvent:
    """session_start Hook 事件。"""

    session_id: str = ""
    session_key: str | None = None
    resumed_from: str | None = None


@dataclass
class PluginHookSessionEndEvent:
    """session_end Hook 事件。"""

    session_id: str = ""
    session_key: str | None = None
    message_count: int = 0
    duration_ms: int | None = None


@dataclass
class PluginHookSubagentContext:
    """Subagent 上下文。"""

    run_id: str | None = None
    child_session_key: str | None = None
    requester_session_key: str | None = None


@dataclass
class PluginHookSubagentSpawningEvent:
    """subagent_spawning Hook 事件。"""

    child_session_key: str = ""
    agent_id: str = ""
    label: str | None = None
    mode: str = "run"
    requester: dict[str, Any] | None = None
    thread_requested: bool = False


@dataclass
class PluginHookSubagentSpawningResult:
    """subagent_spawning Hook 结果。"""

    status: str = "ok"
    thread_binding_ready: bool = False
    error: str | None = None


@dataclass
class PluginHookSubagentDeliveryTargetEvent:
    """subagent_delivery_target Hook 事件。"""

    child_session_key: str = ""
    requester_session_key: str = ""
    requester_origin: dict[str, Any] | None = None
    child_run_id: str | None = None
    spawn_mode: str | None = None
    expects_completion_message: bool = True


@dataclass
class PluginHookSubagentDeliveryTargetResult:
    """subagent_delivery_target Hook 结果。"""

    origin: dict[str, Any] | None = None


@dataclass
class PluginHookSubagentSpawnedEvent:
    """subagent_spawned Hook 事件。"""

    child_session_key: str = ""
    agent_id: str = ""
    label: str | None = None
    mode: str = "run"
    requester: dict[str, Any] | None = None
    thread_requested: bool = False
    run_id: str = ""


@dataclass
class PluginHookSubagentEndedEvent:
    """subagent_ended Hook 事件。"""

    target_session_key: str = ""
    target_kind: str = "subagent"
    reason: str = ""
    send_farewell: bool | None = None
    account_id: str | None = None
    run_id: str | None = None
    ended_at: float | None = None
    outcome: str | None = None
    error: str | None = None


@dataclass
class PluginHookGatewayContext:
    """Gateway 上下文。"""

    port: int | None = None


@dataclass
class PluginHookGatewayStartEvent:
    """gateway_start Hook 事件。"""

    port: int = 0


@dataclass
class PluginHookGatewayStopEvent:
    """gateway_stop Hook 事件。"""

    reason: str | None = None


EventT = TypeVar("EventT")
ResultT = TypeVar("ResultT")

PluginHookHandler = Callable[[EventT, Any], ResultT | None] | Callable[[EventT, Any], "Coroutine[Any, Any, ResultT | None]"]


@dataclass
class PluginHookRegistration:
    """Hook 注册信息。"""

    plugin_id: str
    hook_name: PluginHookName
    handler: PluginHookHandler
    priority: int = 0
    source: str = ""


def is_plugin_hook_name(name: str) -> bool:
    """检查是否为有效的 Hook 名称。"""
    return name in PLUGIN_HOOK_NAMES


PROMPT_INJECTION_HOOK_NAMES = (
    PluginHookName.BEFORE_PROMPT_BUILD,
    PluginHookName.BEFORE_AGENT_START,
)


def is_prompt_injection_hook_name(hook_name: PluginHookName) -> bool:
    """检查是否为 Prompt 注入 Hook。"""
    return hook_name in PROMPT_INJECTION_HOOK_NAMES
