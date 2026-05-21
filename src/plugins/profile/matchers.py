"""@bot 画像查询处理器"""

from nonebot import on_message, logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.rule import to_me

from src.plugins.profile.analyzer import (
    build_relation_graph,
    compute_stats,
    generate_profile_report,
    infer_tags,
)
from src.plugins.profile.models import UserProfile, UserStats
from src.services.database import get_db_session
from src.services.llm_client import create_llm_client
from src.config import load_config

matcher = on_message(rule=to_me(), priority=9, block=True)


def resolve_target(event: GroupMessageEvent) -> int | None:
    """从事件消息中提取被 @ 的目标 user_id（排除 bot 自身）。"""
    for seg in event.get_message():
        if seg.type == "at":
            qq_raw = seg.data["qq"]
            if qq_raw == "all":  # @全体成员，跳过
                continue
            qq = int(qq_raw)
            if qq != event.self_id:
                return qq
    return None


def extract_command_text(event: GroupMessageEvent) -> str:
    """提取消息中的纯文本部分，用于判断命令关键词。"""
    parts: list[str] = []
    for seg in event.get_message():
        if seg.type == "text":
            parts.append(str(seg.data.get("text", "")).strip())
    return " ".join(parts)


async def _get_group_card(bot: Bot, group_id: int, user_id: int) -> str:
    """获取群成员的群名片，取不到则返回 QQ 号"""
    try:
        info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
        return info.get("card") or info.get("nickname") or str(user_id)
    except Exception:
        return str(user_id)


@matcher.handle()
async def handle_profile_query(bot: Bot, event: GroupMessageEvent) -> None:
    cmd_text = extract_command_text(event)

    # 检查是否包含画像相关关键词
    if not any(kw in cmd_text for kw in ("画像", "看看", "profile", "资料")):
        return  # 不匹配命令，忽略

    target_id = resolve_target(event)
    group_id = event.group_id
    logger.info(f"[profile] query: target_id={target_id}, group_id={group_id}, sender_id={event.user_id}")

    # 没 @ 任何人 → 机器人自我介绍
    if target_id is None:
        config = load_config()
        llm_config = config.llm
        api_key = getattr(config, f"{llm_config.provider}_api_key", None) or ""
        client = create_llm_client({
            "provider": llm_config.provider,
            "api_key": api_key,
            "base_url": llm_config.base_url,
            "model": llm_config.model,
        })
        from src.services.llm_router import generate_answer
        about = await generate_answer(
            f"群友让你介绍一下你自己，用{config.bot.persona.name}的身份和口吻回应",
            {"name": config.bot.persona.name, "reply_tone": config.bot.persona.reply_tone},
            client,
        )
        await matcher.finish(about)

    async with get_db_session() as session:
        stats = await compute_stats(target_id, group_id, session)

        if stats.total_messages == 0:
            await matcher.finish("未找到该群友")

        if stats.total_messages < 10:
            await matcher.finish("该群友发言较少，暂时无法生成画像")

        # 构造 LLM 客户端用于标签增强
        llm_client = None
        try:
            cfg = load_config()
            api_key = getattr(cfg, f"{cfg.llm.provider}_api_key", None) or ""
            llm_client = create_llm_client({
                "provider": cfg.llm.provider,
                "api_key": api_key,
                "base_url": cfg.llm.base_url,
                "model": cfg.llm.model,
            })
        except Exception:
            pass

        tags = await infer_tags(target_id, group_id, session, llm_client=llm_client)
        relations_map = await build_relation_graph(group_id, session)
        user_relations = relations_map.get(target_id, {})

        # 解析群昵称
        target_name = await _get_group_card(bot, group_id, target_id)
        relation_names: dict[int, str] = {}
        for uid in user_relations:
            relation_names[uid] = await _get_group_card(bot, group_id, uid)

        profile = UserProfile(
            user_id=target_id,
            group_id=group_id,
            stats=stats,
            tags=tags,
            relations=user_relations,
        )

    report = generate_profile_report(profile, target_name=target_name, relation_names=relation_names)
    await matcher.finish(MessageSegment.reply(event.message_id) + "\n" + report)
