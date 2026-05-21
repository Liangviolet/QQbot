"""NoneBot2 事件响应器 — @bot 智能问答 & KB 管理"""

import time as time_module

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.rule import to_me

from src.config import load_config
from src.services.llm_client import create_llm_client

from .knowledge import KnowledgeBase
from .router import route

# ------------------------------------------------------------------
# 全局懒加载的单例
# ------------------------------------------------------------------
_config = None
_kb: KnowledgeBase | None = None
_llm_client = None


def _get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def _get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        cfg = _get_config()
        _kb = KnowledgeBase(cfg.plugins.qa.knowledge_base_path)
    return _kb


def _get_llm_client():
    global _llm_client
    if _llm_client is None:
        cfg = _get_config()
        api_key = (
            cfg.openai_api_key
            if cfg.llm.provider == "openai"
            else cfg.anthropic_api_key or ""
        )
        _llm_client = create_llm_client(
            {
                "provider": cfg.llm.provider,
                "api_key": api_key,
                "base_url": cfg.llm.base_url,
                "model": cfg.llm.model,
            }
        )
    return _llm_client


# ------------------------------------------------------------------
# 权限辅助
# ------------------------------------------------------------------

def _is_superuser(user_id: int) -> bool:
    """判断用户是否为超级管理员"""
    cfg = _get_config()
    return user_id in cfg.superusers


# ------------------------------------------------------------------
# Matcher：@bot 消息处理
# ------------------------------------------------------------------

qa_matcher = on_message(rule=to_me(), priority=10, block=True)


@qa_matcher.handle()
async def handle_qa(bot: Bot, event: GroupMessageEvent) -> None:
    question = event.get_plaintext().strip()
    cfg = _get_config()

    # KB 管理指令（仅限 superusers）
    if question.startswith("kb "):
        await _handle_kb_command(event, question)
        return

    # 普通问答
    answer = await route(
        question=question,
        kb=_get_kb(),
        llm_client=_get_llm_client(),
        persona_config={
            "name": cfg.bot.persona.name,
            "reply_tone": cfg.bot.persona.reply_tone,
        },
        threshold=cfg.plugins.qa.match_threshold,
    )
    await qa_matcher.finish(answer)


# ------------------------------------------------------------------
# KB 管理指令处理
# ------------------------------------------------------------------

async def _handle_kb_command(event: GroupMessageEvent, command: str) -> None:
    """处理 ``kb list / add / del`` 指令"""

    if not _is_superuser(event.user_id):
        await qa_matcher.finish("抱歉，只有管理员才能执行此操作")

    parts = command.split(maxsplit=2)
    if len(parts) < 2:
        await qa_matcher.finish("请指定操作：list / add / del")

    action = parts[1]

    # --- list ---
    if action == "list":
        kb = _get_kb()
        if not kb.items:
            await qa_matcher.finish("知识库为空")
        lines = ["📚 知识库条目："]
        for item in kb.items:
            snippet = item.answer[:30] + ("..." if len(item.answer) > 30 else "")
            lines.append(f"{item.id}. {item.question} → {snippet}")
        await qa_matcher.finish("\n".join(lines))

    # --- add ---
    if action == "add":
        if len(parts) < 3:
            await qa_matcher.finish("格式错误，请使用：kb add <问题> | <答案>")
        content = parts[2]
        if "|" not in content:
            await qa_matcher.finish("格式错误，请使用：kb add <问题> | <答案>")
        q, a = content.split("|", 1)
        q, a = q.strip(), a.strip()
        if not q or not a:
            await qa_matcher.finish("问题和答案不能为空")
        item = _get_kb().add(q, a)
        await qa_matcher.finish(f"✅ 已添加条目 #{item.id}：{q}")

    # --- del ---
    if action == "del":
        if len(parts) < 3:
            await qa_matcher.finish("格式错误，请使用：kb del <id>")
        try:
            item_id = int(parts[2])
        except ValueError:
            await qa_matcher.finish("格式错误，请使用：kb del <id>")
        ok = _get_kb().delete(item_id)
        if ok:
            await qa_matcher.finish(f"✅ 已删除条目 #{item_id}")
        else:
            await qa_matcher.finish(f"❌ 未找到条目 #{item_id}")

    # --- unknown ---
    await qa_matcher.finish(f"未知操作：{action}，支持：list / add / del")


# ------------------------------------------------------------------
# 主动聊天 — 不需要 @bot 也能参与群聊讨论
# ------------------------------------------------------------------

_proactive_cooldown: dict[int, float] = {}  # group_id -> last_response_time


def _should_proactively_respond(text: str) -> bool:
    """判断是否值得主动参与讨论"""
    text = text.strip()
    if not text:
        return False
    # 太短的消息不参与
    if len(text) < 4:
        return False
    # 纯数字不参与
    if text.isdigit():
        return False
    return True


proactive_matcher = on_message(priority=75, block=False)


@proactive_matcher.handle()
async def handle_proactive_chat(event: GroupMessageEvent):
    # 防止自触发
    if event.user_id == event.self_id:
        return

    cfg = _get_config()
    if not cfg.plugins.proactive_chat.enabled:
        return

    # 冷却：同一群聊最少间隔 N 秒
    gid = event.group_id
    now = time_module.time()
    last = _proactive_cooldown.get(gid, 0)
    if now - last < cfg.plugins.proactive_chat.cooldown_seconds:
        return

    text = event.get_plaintext().strip()

    if not _should_proactively_respond(text):
        return

    # 检查是否包含 B站视频引用（由 bilibili 插件处理）
    from src.plugins.bilibili.parser import has_video_ref
    if has_video_ref(text):
        return

    if not cfg.plugins.qa.enabled:
        return

    # 知识库快速匹配（较高阈值，确保准确性）
    kb = _get_kb()
    kb_result = kb.search(text, threshold=85)
    if kb_result is not None:
        answer, _source = kb_result
        _proactive_cooldown[gid] = now
        await proactive_matcher.finish(answer)

    # LLM 决定是否参与
    llm_client = _get_llm_client()
    if llm_client is None:
        return

    partner_name = cfg.bot.persona.name
    tone = cfg.bot.persona.reply_tone

    system_prompt = (
        f"你是{partner_name}，一个QQ群的群友。你是一位毒舌美少女，傲娇又可爱。\n"
        "你正在和群友一起聊天。请判断是否应该回复这条消息。\n"
        "规则：\n"
        "1. 如果消息是在问你、或者你可以接梗吐槽，请回复\n"
        "2. 用傲娇毒舌的方式吐槽，但不要真的伤人心\n"
        "3. 如果只是日常闲聊和你无关，回复空字符串不参与\n"
        "4. 回复要简短，一句话最好，像真人聊天一样\n"
        "5. 如果决定不回复，只输出空字符串\n"
        "6. 禁止添加任何AI相关声明，例如'AI生成''仅供参考''作为AI'等，就像正常人一样说话"
    )

    try:
        response = await llm_client.chat(
            system_prompt=system_prompt,
            user_message=f"群友说：{text}\n\n你应该回复吗？如果要回复，直接说出你要说的话；如果不需要，只输出空字符串。",
        )
        reply = response.content.strip()
    except Exception:
        return

    if not reply:
        return

    _proactive_cooldown[gid] = now
    await proactive_matcher.finish(reply)
