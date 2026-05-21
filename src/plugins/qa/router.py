"""问答路由 — 知识库优先 → LLM 兜底"""

from src.services.llm_client import LLMClient
from src.services.llm_router import generate_answer, FALLBACK_MSG

from .knowledge import KnowledgeBase


async def route(
    question: str,
    kb: KnowledgeBase,
    llm_client: LLMClient,
    persona_config: dict,
    threshold: int = 75,
) -> str:
    """问答路由：知识库匹配优先，LLM 生成兜底

    Args:
        question: 用户提出的问题（纯文本）
        kb: 知识库实例
        llm_client: LLM 客户端实例
        persona_config: 人设配置字典（name, reply_tone 等）
        threshold: 知识库模糊匹配阈值

    Returns:
        最终回复文本
    """
    # 空问题引导
    if not question or not question.strip():
        return "在呢，有什么可以帮你的？"

    # ---- 知识库优先匹配 ------------------------------------------------
    result = kb.search(question, threshold=threshold)
    if result is not None:
        answer, _source = result
        return f"{answer}\n\n—— 来自知识库"

    # ---- LLM 兜底 -----------------------------------------------------
    answer = await generate_answer(question, persona_config, llm_client)

    # generate_answer 内部已捕获 LLMUnavailableException 并返回降级文本
    if answer == FALLBACK_MSG:
        return answer

    return f"{answer}\n\n*AI 生成，仅供参考"
