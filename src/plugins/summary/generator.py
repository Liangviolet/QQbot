"""U6 每日群聊总结生成器 — 热词、活跃榜、潜水提醒"""

import jieba
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, distinct

from src.models.message import GroupMessage
from src.models.summary import SummaryRecord
from src.services.database import get_db_session

# 默认中文停用词集
_DEFAULT_STOPWORDS: set[str] = {
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人",
    "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
    "它", "们", "那", "啥", "吗", "啊", "呢", "吧", "嗯", "哦",
    "哈", "呀", "啦", "嘛", "这个", "那个", "什么", "怎么", "可以",
    "因为", "所以", "但是", "然后", "如果", "虽然", "而且", "或者",
    "还是", "只是", "不是", "就是", "真的", "觉得", "知道",
    "已经", "比较", "非常", "一直", "一些", "开始", "最后", "现在",
    "时候", "之后", "之前", "这里", "那里", "为什么", "多少",
    "每", "某", "个", "种", "些", "点", "多", "少", "大",
    "小", "来", "回", "过", "把", "被", "让", "给", "对", "跟",
    "从", "向", "在", "到", "于", "与", "以", "为", "按", "照",
    "通过", "用", "作", "做", "能", "够", "想", "要", "需", "必须",
}

def _get_day_range(dt: datetime) -> tuple[int, int]:
    """获取指定日期的时间戳范围 [start_of_day, start_of_next_day)。

    返回 Unix 时间戳（秒），用于 SQL 的 >= 和 < 查询。
    """
    start = datetime(dt.year, dt.month, dt.day, tzinfo=dt.tzinfo)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


async def get_hot_words(
    group_id: int,
    date: datetime,
    top_n: int = 5,
    stopwords: Optional[set[str]] = None,
    session_maker=None,
) -> list[tuple[str, int]]:
    """获取指定群组在指定日期的最热词汇 TOP N。

    Args:
        group_id: 群组 ID
        date: 日期（年月日有效，时分秒被忽略）
        top_n: 返回前 N 个热词，默认 5
        stopwords: 自定义停用词集，不传则使用内置停用词
        session_maker: 测试用 session maker，不传则使用全局默认

    Returns:
        list of (word, count)
    """
    if stopwords is None:
        stopwords = _DEFAULT_STOPWORDS

    start_ts, end_ts = _get_day_range(date)

    async with get_db_session(session_maker) as session:
        result = await session.execute(
            select(GroupMessage.plain_text)
            .where(
                GroupMessage.group_id == group_id,
                GroupMessage.timestamp >= start_ts,
                GroupMessage.timestamp < end_ts,
                GroupMessage.plain_text != "",
            )
        )
        texts = result.scalars().all()

    word_counter: Counter = Counter()
    for text in texts:
        words = jieba.lcut(text)
        for word in words:
            word = word.strip()
            if len(word) < 2 or word in stopwords:
                continue
            word_counter[word] += 1

    return word_counter.most_common(top_n)


async def get_active_speakers(
    group_id: int,
    date: datetime,
    top_n: int = 3,
    session_maker=None,
) -> list[tuple[int, int]]:
    """获取指定群组在指定日期发言最活跃的用户 TOP N。

    Returns:
        list of (user_id, message_count)
    """
    start_ts, end_ts = _get_day_range(date)

    async with get_db_session(session_maker) as session:
        stmt = (
            select(
                GroupMessage.user_id,
                func.count(GroupMessage.id).label("msg_count"),
            )
            .where(
                GroupMessage.group_id == group_id,
                GroupMessage.timestamp >= start_ts,
                GroupMessage.timestamp < end_ts,
            )
            .group_by(GroupMessage.user_id)
            .order_by(func.count(GroupMessage.id).desc())
            .limit(top_n)
        )
        result = await session.execute(stmt)
        return [(row.user_id, row.msg_count) for row in result]


async def get_lurkers(
    group_id: int,
    date: datetime,
    session_maker=None,
) -> list[int]:
    """获取今日未发言但过去 7 天有发言的用户列表（潜水用户）。

    Returns:
        list of user_id
    """
    start_ts, end_ts = _get_day_range(date)
    past_7d_start = start_ts - 7 * 24 * 3600

    async with get_db_session(session_maker) as session:
        past_result = await session.execute(
            select(distinct(GroupMessage.user_id))
            .where(
                GroupMessage.group_id == group_id,
                GroupMessage.timestamp >= past_7d_start,
                GroupMessage.timestamp < start_ts,
            )
        )
        past_users = {row[0] for row in past_result}

        today_result = await session.execute(
            select(distinct(GroupMessage.user_id))
            .where(
                GroupMessage.group_id == group_id,
                GroupMessage.timestamp >= start_ts,
                GroupMessage.timestamp < end_ts,
            )
        )
        today_users = {row[0] for row in today_result}

    lurkers = list(past_users - today_users)
    lurkers.sort()
    return lurkers


def _format_template(
    hot_words: list[tuple[str, int]],
    active_speakers: list[tuple[int, int]],
    lurkers: list[int],
) -> str:
    """使用纯模板格式生成总结文本。"""
    lines = ["📊 今日群聊总结"]

    if hot_words:
        hw_str = "、".join(f"{w}({c}次)" for w, c in hot_words)
        lines.append(f"热词 TOP {len(hot_words)}：{hw_str}")
    else:
        lines.append("热词 TOP：暂无数据")

    if active_speakers:
        sp_str = "、".join(
            f"用户{u}({c}条)" for u, c in active_speakers
        )
        lines.append(f"发言 TOP {len(active_speakers)}：{sp_str}")
    else:
        lines.append("发言排行：暂无数据")

    if lurkers:
        lk_str = "、".join(f"用户{u}" for u in lurkers)
        lines.append(f"潜水提醒：{lk_str}今天还没说话哦")
    else:
        lines.append("潜水提醒：今天大家都说话了，继续保持！")

    return "\n".join(lines)


async def generate_summary(
    group_id: int,
    date: datetime,
    llm_client=None,
    persona_config: Optional[dict] = None,
    session_maker=None,
) -> str:
    """生成每日群聊总结。

    Args:
        group_id: 群组 ID
        date: 日期
        llm_client: LLM 客户端实例（可选），提供时尝试 LLM 润色
        persona_config: 人设配置（可选），与 llm_client 搭配使用
        session_maker: 测试用 session maker

    Returns:
        总结文本
    """
    hot_words = await get_hot_words(group_id, date, session_maker=session_maker)
    active_speakers = await get_active_speakers(group_id, date, session_maker=session_maker)
    lurkers = await get_lurkers(group_id, date, session_maker=session_maker)

    # 当日无消息
    if not hot_words and not active_speakers:
        return "今天群里还没有消息哦～"

    # 尝试 LLM 润色
    if llm_client is not None and persona_config is not None:
        from src.services.llm_router import generate_answer, FALLBACK_MSG

        stats_parts: list[str] = []
        if hot_words:
            hw = "、".join(f"{w}({c})" for w, c in hot_words)
            stats_parts.append(f"热词排行 TOP {len(hot_words)}：{hw}")
        if active_speakers:
            asp = "、".join(f"用户{u}({c}条)" for u, c in active_speakers)
            stats_parts.append(f"活跃用户 TOP {len(active_speakers)}：{asp}")
        if lurkers:
            lurkers_str = "、".join(f"用户{u}" for u in lurkers)
            stats_parts.append(f"潜水用户：{lurkers_str}")

        question = "请根据以下群聊统计数据生成一段自然流畅、友好的群聊总结：\n" + "\n".join(stats_parts)
        result = await generate_answer(question, persona_config, llm_client)
        if result != FALLBACK_MSG:
            return result

    # LLM 不可用或返回降级消息 -> 纯模板
    return _format_template(hot_words, active_speakers, lurkers)


async def get_last_summary_date(
    group_id: int,
    session_maker=None,
) -> Optional[str]:
    """获取指定群组最近一次总结日期。

    Returns:
        ISO 日期字符串如 "2026-05-21"，或 None
    """
    async with get_db_session(session_maker) as session:
        result = await session.execute(
            select(SummaryRecord.date)
            .where(SummaryRecord.group_id == group_id)
            .order_by(SummaryRecord.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def set_last_summary_date(
    group_id: int,
    date: str,
    session_maker=None,
) -> None:
    """记录指定群组的总结日期（幂等，重复调用不会报错）。

    Args:
        group_id: 群组 ID
        date: ISO 日期字符串如 "2026-05-21"
        session_maker: 测试用 session maker
    """
    async with get_db_session(session_maker) as session:
        result = await session.execute(
            select(SummaryRecord).where(
                SummaryRecord.group_id == group_id,
                SummaryRecord.date == date,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            session.add(SummaryRecord(group_id=group_id, date=date))
