"""统计计算、标签推断、关系图构建"""

import re
from collections import Counter
from datetime import datetime
from typing import Optional

import jieba
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.message import GroupMessage
from src.plugins.profile.models import UserProfile, UserStats

# ── 预定义标签关键词映射 ──────────────────────────────────────────
TOPIC_TAG_MAP: dict[str, str] = {
    "原神": "游戏",
    "王者": "游戏",
    "吃鸡": "游戏",
    "游戏": "游戏",
    "LOL": "游戏",
    "Python": "编程",
    "Java": "编程",
    "代码": "编程",
    "编程": "编程",
    "前端": "编程",
    "动漫": "动漫",
    "番剧": "动漫",
    "漫画": "动漫",
    "二次元": "动漫",
    "电影": "影视",
    "电视剧": "影视",
    "综艺": "影视",
    "股票": "财经",
    "基金": "财经",
    "理财": "财经",
    "健身": "运动",
    "跑步": "运动",
    "篮球": "运动",
}

# ── 简易中文停用词 ───────────────────────────────────────────────
_STOP_WORDS: set[str] = {
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人",
    "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
    "它", "们", "那", "里", "就", "吗", "啊", "呢", "吧", "嗯",
    "哦", "哈", "啦", "呀", "嘛", "哟", "的", "了", "是", "在",
    "不", "我", "有", "和", "就", "也", "被", "把", "让", "从",
    "什么", "怎么", "为什么", "可以", "这个", "那个", "因为", "所以",
    "但是", "如果", "然后", "而且", "或者", "虽然", "还是", "不是",
    "就是", "只是", "但是", "还是", "没有", "已经", "可以", "可能",
    "应该", "能够", "需要", "知道", "觉得", "看到", "听到", "想到",
    "一个", "一些", "什么", "时候", "地方", "这样", "那样", "怎么",
    "如何", "哪个", "哪里", "谁", "为什么", "几", "多少",
}

# ── 向 jieba 注册标签关键词（确保它们作为独立词被识别） ────────
for _kw in TOPIC_TAG_MAP:
    jieba.add_word(_kw)

# ── CQ at 码正则 ─────────────────────────────────────────────────
_CQ_AT_RE = re.compile(r"\[CQ:at,qq=(\d+)\]")


def parse_cq_ats(raw_message: str) -> list[int]:
    """从 raw_message 中解析所有被 @ 的 QQ 号。"""
    return [int(uid) for uid in _CQ_AT_RE.findall(raw_message)]


# ── 统计计算 ──────────────────────────────────────────────────────
async def compute_stats(
    user_id: int,
    group_id: int,
    session: AsyncSession,
) -> UserStats:
    """计算指定用户在群内的发言统计。"""
    stmt = (
        select(GroupMessage)
        .where(
            GroupMessage.user_id == user_id,
            GroupMessage.group_id == group_id,
        )
        .order_by(GroupMessage.timestamp)
    )
    result = await session.execute(stmt)
    messages = result.scalars().all()

    if not messages:
        return UserStats()

    total = len(messages)
    timestamps = [m.timestamp for m in messages]

    # 日均发言
    first_ts = datetime.fromtimestamp(timestamps[0])
    last_ts = datetime.fromtimestamp(timestamps[-1])
    days_span = max((last_ts - first_ts).days, 1)
    avg_daily = round(total / days_span, 2)

    # 活跃时段分布
    hourly_dist: dict[int, int] = {}
    for t in timestamps:
        hour = datetime.fromtimestamp(t).hour
        hourly_dist[hour] = hourly_dist.get(hour, 0) + 1

    # 高频词汇
    all_text = " ".join(m.plain_text for m in messages if m.plain_text.strip())
    words = jieba.lcut(all_text)
    filtered = [
        w.strip()
        for w in words
        if w.strip() and w.strip() not in _STOP_WORDS and len(w.strip()) > 1
    ]
    word_counts = Counter(filtered)
    top_words = word_counts.most_common(20)

    return UserStats(
        total_messages=total,
        avg_daily=avg_daily,
        hourly_distribution=hourly_dist,
        top_words=top_words,
    )


# ── 兴趣标签推断 ──────────────────────────────────────────────────
async def infer_tags(
    user_id: int,
    group_id: int,
    session: AsyncSession,
    min_occurrences: int = 3,
    llm_client: Optional[object] = None,
) -> list[str]:
    """推断用户在群内的兴趣标签。

    规则层：分词后匹配 TOPIC_TAG_MAP。
    LLM 层（可选）：当 llm_client 传入时尝试用 LLM 补充标签。
    """
    stmt = select(GroupMessage.plain_text).where(
        GroupMessage.user_id == user_id,
        GroupMessage.group_id == group_id,
    )
    result = await session.execute(stmt)
    texts = [row[0] for row in result.fetchall() if row[0].strip()]

    if not texts:
        return []

    # ── 规则层 ────────────────────────────────────────────────
    tag_counter: Counter[str] = Counter()
    for text in texts:
        words = jieba.lcut(text)
        for word in words:
            tag = TOPIC_TAG_MAP.get(word)
            if tag is not None:
                tag_counter[tag] += 1

    tags = [tag for tag, cnt in tag_counter.items() if cnt >= min_occurrences]

    # ── LLM 可选增强层 ─────────────────────────────────────────
    if llm_client is not None:
        try:
            sample_texts = texts[-20:]  # 取最近 20 条作为样本
            user_content = "\n".join(f"- {t}" for t in sample_texts)
            system_prompt = (
                "你是一个兴趣标签推断助手。根据用户的历史发言，推断该用户的兴趣标签。"
                f"已有标签（基于规则）：{tags}。"
                "请补充最多 3 个额外的兴趣标签，以逗号分隔返回。如果没有要补充的，返回空。"
            )
            resp = await llm_client.chat(
                system_prompt=system_prompt,
                user_message=user_content,
                max_tokens=128,
                temperature=0.3,
            )
            llm_tags = [t.strip() for t in resp.content.split(",") if t.strip()]
            for t in llm_tags:
                if t not in tags:
                    tags.append(t)
        except Exception:
            # LLM 不可用时退回纯规则结果
            pass

    return tags


# ── 关系图构建 ────────────────────────────────────────────────────
async def build_relation_graph(
    group_id: int,
    session: AsyncSession,
) -> dict[int, dict[int, int]]:
    """构建群内 @mention 关系图 {sender_id: {target_id: count}}。"""
    stmt = (
        select(GroupMessage.user_id, GroupMessage.raw_message)
        .where(GroupMessage.group_id == group_id)
        .order_by(GroupMessage.timestamp)
    )
    result = await session.execute(stmt)

    graph: dict[int, dict[int, int]] = {}
    for sender_id, raw_msg in result.fetchall():
        targets = parse_cq_ats(raw_msg)
        if not targets:
            continue
        if sender_id not in graph:
            graph[sender_id] = {}
        for target_id in targets:
            graph[sender_id][target_id] = graph[sender_id].get(target_id, 0) + 1

    return graph


# ── 报告生成 ──────────────────────────────────────────────────────
def _format_peak_hours(hourly: dict[int, int]) -> str:
    """格式化最活跃时段描述。"""
    if not hourly:
        return "暂无数据"
    # 找出最活跃的时段窗口
    sorted_hours = sorted(hourly.items())
    peak_hour = max(sorted_hours, key=lambda x: x[1])[0]
    end_hour = min(peak_hour + 2, 23)
    return f"{peak_hour}:00-{end_hour}:00 点"


def _format_relations(relations: dict[int, int], name_map: dict[int, str]) -> str:
    """格式化互动关系文本，显示群昵称而非 QQ 号。"""
    if not relations:
        return "暂无互动数据"
    sorted_rels = sorted(relations.items(), key=lambda x: -x[1])[:10]
    lines = []
    for target_id, count in sorted_rels:
        name = name_map.get(target_id, str(target_id))
        lines.append(f"与 {name} 互动 {count} 次")
    return "\n".join(lines)


def generate_profile_report(profile: UserProfile, target_name: str = "", relation_names: dict[int, str] | None = None) -> str:
    """生成格式化的画像报告文本。

    Args:
        profile: 用户画像数据
        target_name: 目标用户的群名片，为空则用 QQ 号
        relation_names: 互动对象的群名片映射，为空则显示 QQ 号
    """
    stats = profile.stats
    peak = _format_peak_hours(stats.hourly_distribution)
    relations_text = _format_relations(profile.relations, relation_names or {})

    tags_text = " ".join(f"#{t}" for t in profile.tags) if profile.tags else "暂无标签信息"

    # 兴趣标签后续加上关系网络部分
    lines = [
        f"📋 {target_name or profile.user_id} 的群聊画像",
        "────────────",
        "📊 发言统计",
        f"总发言：{stats.total_messages} 条 | 日均：{stats.avg_daily} 条",
        f"最活跃时段：{peak}",
        "",
        "🏷 兴趣标签",
        tags_text,
    ]

    if profile.relations:
        lines.extend([
            "",
            "🔗 互动关系",
            relations_text,
        ])

    return "\n".join(lines)
