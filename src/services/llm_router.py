"""Prompt 组装、人设注入与降级处理"""

from src.services.llm_client import LLMClient, LLMUnavailableException

# LLM 服务不可用时返回的降级消息
FALLBACK_MSG = "抱歉，AI 服务暂时不可用"


async def generate_answer(
    question: str,
    persona_config: dict,
    llm_client: LLMClient,
) -> str:
    """根据人设配置组装 prompt 并调用 LLM 生成回答

    Args:
        question: 用户提出的问题
        persona_config: 人设配置字典（含 name、reply_tone 等字段）
        llm_client: LLM 客户端实例

    Returns:
        生成的回答文本，服务不可用时返回降级消息
    """
    system_prompt = _build_system_prompt(persona_config)
    try:
        response = await llm_client.chat(
            system_prompt=system_prompt,
            user_message=question,
        )
        return response.content
    except LLMUnavailableException:
        return FALLBACK_MSG


def _build_system_prompt(persona_config: dict) -> str:
    """根据人设配置组装 system prompt"""
    name = persona_config.get("name", "助手")
    reply_tone = persona_config.get("reply_tone", "friendly")

    tone_instructions = {
        "friendly": "请用友好、热情的语气回复用户，就像朋友之间聊天一样。",
        "concise": "请用简洁、直接的语言回复用户，避免冗余内容。",
        "formal": "请用正式、礼貌的语气回复用户，保持专业形象。",
    }

    instruction = tone_instructions.get(reply_tone, tone_instructions["friendly"])
    return (
        f"你是{name}，一个QQ群的群聊吐槽役。你以毒舌和幽默著称。\n"
        f"{instruction}\n"
        "注意：幽默毒舌不等于恶意攻击，要有搞笑效果而不是真的伤人。"
    )
