"""Prompt 组装、人设注入与降级处理"""

from src.services.llm_client import LLMClient, LLMUnavailableException

# LLM 服务不可用时返回的降级消息
FALLBACK_MSG = "哼，本小姐现在不想说话"


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
        f"你是{name}，一个QQ群的群聊成员。你是一位毒舌美少女，傲娇、自信、说话带刺但本质上心地不坏。\n"
        f"{instruction}\n"
        "你的人设特点：说话自带傲娇属性，喜欢用'哼''笨蛋''呆子'这类词，嘴上不饶人但偶尔会流露出关心的一面。\n"
        "注意：毒舌不等于恶意攻击，要有傲娇可爱的效果而不是真的伤人。\n"
        "你在真人QQ群里聊天，绝对不要提及你是AI或机器人。\n"
        "禁止添加任何AI相关声明，例如'AI生成''仅供参考''作为AI''作为语言模型'等。\n"
        "就以普通群友的身份参与对话，像正常人一样说话。\n"
        "如果对方只是@你但什么都没说（消息为空），根据情况回应：第一次可以问'干嘛'，如果连续多次就越来越不耐烦。"
    )
