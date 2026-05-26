"""声明式模型能力表，针对 OpenAI 兼容 Provider。

这是唯一知道「哪个模型 ID 拒绝哪个 API 参数」或「需要哪种结构化输出方法」的地方。
LLM Client 子类通过 get_capabilities(model_name) 查询，而非硬编码 model-name 的 if 分支。
新增模型（或新 quirk）只需编辑此表，无需改动 Client 代码。

模式借鉴自 DeepSeek 官方集成指南中的 per-model compat: 标志
（如 Oh My Pi 配置中记录的 supportsToolChoice、requiresReasoningContentForToolCalls）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


# 支持的结构化输出方法四选一：
# function_calling → 使用 tools 参数；依赖 supports_tool_choice
# json_mode       → 使用 response_format={"type":"json_object"}
# json_schema     → 使用 response_format={"type":"json_schema",...}
# none            → 不支持结构化输出；调用方降级为自由文本
StructuredMethod = Literal[
    "function_calling",
    "json_mode",
    "json_schema",
    "none",
]


@dataclass(frozen=True)
class ModelCapabilities:
    """声明单个模型在 API 层面支持哪些能力。

    所有 OpenAI 兼容 Provider 的 Client 在遇到结构化输出、tool_choice 等参数时，
    均查询此表而非硬编码 if-elif，从而将「模型兼容性知识」集中管理。

    Attributes:
        supports_tool_choice: 模型是否接受 tool_choice 参数。
            DeepSeek V4/MiniMax M2.x 等会对此参数返回 400，
            NormalizedChatOpenAI.with_structured_output() 会抑制此参数。
        supports_json_mode: 是否支持 json_mode（response_format="json_object"）。
        supports_json_schema: 是否支持带 schema 的 json_mode。
        preferred_structured_method: 偏好的结构化输出方法。
        requires_reasoning_content_roundtrip:
            DeepSeek thinking 模型在多轮对话中必须回传 reasoning_content，
            否则下一轮请求返回 400。参见 DeepSeekChatOpenAI._get_request_payload()。
        requires_reasoning_split:
            MiniMax M2.x reasoning 模型需要 reasoning_split=True，
            让 <thinking> 块落入 reasoning_details 而非污染 message.content。
            非 reasoning 的 MiniMax 模型（Coding Plan、Text-01）会拒绝此参数。
    """

    supports_tool_choice: bool
    supports_json_mode: bool
    supports_json_schema: bool
    preferred_structured_method: StructuredMethod
    requires_reasoning_content_roundtrip: bool = False
    requires_reasoning_split: bool = False


# DeepSeek thinking 模型接受 tools 数组，但拒绝 tool_choice 参数
#（官方 Oh My Pi 集成指南 + issue #678 的 400 响应验证）。
# 官方 tool-calling 示例（api-docs.deepseek.com/guides/tool_calls）
# 只传 tools=[...] 不传 tool_choice；此处通过 supports_tool_choice=False
# 让 NormalizedChatOpenAI 抑制该参数，复现官方示例行为。
_DEEPSEEK_THINKING = ModelCapabilities(
    supports_tool_choice=False,
    supports_json_mode=True,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
    requires_reasoning_content_roundtrip=True,
)

# DeepSeek 普通聊天模型：支持 tool_choice，无特殊quirk
_DEEPSEEK_CHAT = ModelCapabilities(
    supports_tool_choice=True,
    supports_json_mode=True,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
)

# MiniMax M2.x reasoning 模型接受 tools 数组，但 tool_choice 被限制为
# 枚举 {"none", "auto"}（platform.minimax.io/docs/api-reference/text-post）。
# LangChain function_calling 路径发送的是 function-spec dict，
# MiniMax 同样返回 400 — 与 DeepSeek 问题相同。
# supports_tool_choice=False 使 NormalizedChatOpenAI 抑制该参数，
# schema 仍作为 tool 发送。M2.x 不支持 json_mode（仅 MiniMax-Text-01 支持）。
_MINIMAX_THINKING = ModelCapabilities(
    supports_tool_choice=False,
    supports_json_mode=False,
    supports_json_schema=False,
    preferred_structured_method="function_calling",
    requires_reasoning_split=True,
)

# 未知模型的默认能力：假设支持所有能力，
# 这样新模型上线无需修改此表即可正常运行
_DEFAULT = ModelCapabilities(
    supports_tool_choice=True,
    supports_json_mode=True,
    supports_json_schema=True,
    preferred_structured_method="function_calling",
)


# 精确 ID 优先于 pattern 匹配
_BY_ID: dict[str, ModelCapabilities] = {
    "deepseek-chat": _DEEPSEEK_CHAT,
    "deepseek-reasoner": _DEEPSEEK_THINKING,
    "deepseek-v4-flash": _DEEPSEEK_THINKING,
    "deepseek-v4-pro": _DEEPSEEK_THINKING,
    # MiniMax 官方模型阵容（platform.minimax.io/docs/api-reference/text-openai-api）
    # 所有 M2.x 版本共享同一套 thinking 模型能力
    "MiniMax-M2.7": _MINIMAX_THINKING,
    "MiniMax-M2.7-highspeed": _MINIMAX_THINKING,
    "MiniMax-M2.5": _MINIMAX_THINKING,
    "MiniMax-M2.5-highspeed": _MINIMAX_THINKING,
    "MiniMax-M2.1": _MINIMAX_THINKING,
    "MiniMax-M2.1-highspeed": _MINIMAX_THINKING,
    "MiniMax-M2": _MINIMAX_THINKING,
}

# 前向兼容 pattern：新模型 ID 自动继承 thinking 模型的 quirk
# deepseek-v5-* / deepseek-reasoner-* / MiniMax-M3* 等新版本无需修改此表
_BY_PATTERN: list[tuple[re.Pattern[str], ModelCapabilities]] = [
    (re.compile(r"^deepseek-v\d"), _DEEPSEEK_THINKING),
    (re.compile(r"^deepseek-reasoner"), _DEEPSEEK_THINKING),
    (re.compile(r"^MiniMax-M\d"), _MINIMAX_THINKING),
]


def get_capabilities(model_name: str) -> ModelCapabilities:
    """根据模型名解析其 API 能力。

    查询顺序：精确 ID → pattern 正则匹配 → 默认配置。
    保证任何模型都能拿到能力表，不会返回 None。
    """
    if model_name in _BY_ID:
        return _BY_ID[model_name]
    for pattern, caps in _BY_PATTERN:
        if pattern.match(model_name):
            return caps
    return _DEFAULT
