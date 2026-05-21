"""@bot 画像查询处理器"""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent
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

matcher = on_message(rule=to_me(), priority=10)


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


@matcher.handle()
async def handle_profile_query(event: GroupMessageEvent) -> None:
    cmd_text = extract_command_text(event)

    # 检查是否包含画像相关关键词
    if not any(kw in cmd_text for kw in ("画像", "看看", "profile", "资料")):
        return  # 不匹配命令，忽略

    target_id = resolve_target(event)
    if target_id is None:
        await matcher.finish("请 @ 你要查询的群友")

    group_id = event.group_id

    # 查询数据并生成画像
    async with get_db_session() as session:
        stats = await compute_stats(target_id, group_id, session)

        if stats.total_messages == 0:
            await matcher.finish("未找到该群友")

        if stats.total_messages < 10:
            await matcher.finish("该群友发言较少，暂时无法生成画像")

        tags = await infer_tags(target_id, group_id, session)
        relations_map = await build_relation_graph(group_id, session)
        user_relations = relations_map.get(target_id, {})

        profile = UserProfile(
            user_id=target_id,
            group_id=group_id,
            stats=stats,
            tags=tags,
            relations=user_relations,
        )

    report = generate_profile_report(profile)
    await matcher.finish(MessageSegment.reply(event.message_id) + "\n" + report)
