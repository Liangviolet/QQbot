"""B站 BV 号检测与 AI 摘要请求"""

import time

import httpx
from nonebot import on_message, logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.rule import to_me, Rule

from src.plugins.bilibili.parser import extract_bv_ids, extract_all_video_ids, has_video_ref, fetch_video_info, VideoInfo
from src.plugins.bilibili.renderer import format_multi_video_cards, format_bv_limit_warning
from src.config import load_config
from src.services.cache import TTLCache
from src.services.llm_client import create_llm_client, LLMUnavailableException

_config = load_config().plugins.bilibili

# group_id -> (timestamp, bvid)  上下文，供 @bot 总结使用
_group_bv: dict[str, tuple[float, str]] = {}

# 视频信息缓存
_video_cache = TTLCache[VideoInfo](ttl=_config.video_cache_ttl)

# 共享 HTTP 客户端
_client = httpx.AsyncClient(timeout=10.0)


def _has_bv() -> Rule:
    async def _check(event: GroupMessageEvent) -> bool:
        return has_video_ref(event.get_plaintext())
    return Rule(_check)


bv_matcher = on_message(rule=_has_bv(), priority=90, block=False)

summary_matcher = on_message(rule=to_me(), priority=8, block=False)


async def _get_video_info(bvid: str) -> VideoInfo | None:
    """获取视频信息，优先从缓存读取"""
    cached = _video_cache.get(bvid)
    if cached is not None:
        return cached
    info = await fetch_video_info(bvid, _client)
    if info is not None:
        _video_cache.set(bvid, info)
    return info


@bv_matcher.handle()
async def handle_bv(event: GroupMessageEvent):
    # 防止自触发
    if event.user_id == event.self_id:
        return

    text = event.get_plaintext()
    logger.info(f"[bilibili] received message: {text[:50]}")
    all_bv_ids = await extract_all_video_ids(text, _client, max_count=_config.max_bv_per_message)
    logger.info(f"[bilibili] extracted video IDs: {all_bv_ids}")
    if not all_bv_ids:
        # 可能是 b23 短链解析失败之类的，直接忽略
        return

    # 额外检测所有 BV 号用于超限提示
    total_bv = len(extract_bv_ids(text, max_count=100))
    infos: list[VideoInfo] = []
    for bvid in all_bv_ids:
        logger.info(f"[bilibili] fetching: {bvid}")
        info = await _get_video_info(bvid)
        logger.info(f"[bilibili] result for {bvid}: {'ok' if info else 'None'}")
        if info is not None:
            infos.append(info)
            _group_bv[str(event.group_id)] = (time.time(), bvid)

    if not infos:
        logger.info("[bilibili] no valid infos, returning")
        return

    msg = format_multi_video_cards(infos)
    if total_bv > _config.max_bv_per_message:
        msg += MessageSegment.text("\n" + format_bv_limit_warning(total_bv, _config.max_bv_per_message))
    logger.info("[bilibili] sending response")
    await bv_matcher.finish(msg)


@summary_matcher.handle()
async def handle_summary(event: GroupMessageEvent):
    text = event.get_plaintext().strip()
    if text != "总结":
        return

    group_id = str(event.group_id)
    now = time.time()

    # 检查上下文是否存在且未过期
    if group_id not in _group_bv:
        await summary_matcher.finish("请发送或引用BV号")
        return

    timestamp, bvid = _group_bv[group_id]
    if now - timestamp > _config.summary_context_ttl:
        del _group_bv[group_id]
        await summary_matcher.finish("请发送或引用BV号")
        return

    info = await _get_video_info(bvid)
    if info is None:
        await summary_matcher.finish("无法获取视频信息")
        return

    # 调用 LLM 生成摘要
    config = load_config()
    llm_config = config.llm
    api_key = getattr(config, f"{llm_config.provider}_api_key", None) or ""
    llm_client = create_llm_client({
        "provider": llm_config.provider,
        "api_key": api_key,
        "base_url": llm_config.base_url,
        "model": llm_config.model,
    })

    system_prompt = "你是一个视频摘要助手。请用简洁的语言总结B站视频的关键信息。"
    try:
        response = await llm_client.chat(
            system_prompt=system_prompt,
            user_message=(
                f"请为以下B站视频生成一段简洁的摘要：\n"
                f"标题：{info.title}\n"
                f"UP主：{info.author}"
            ),
        )
        summary = response.content
    except LLMUnavailableException:
        summary = "暂时无法获取摘要，等会儿再试试吧"

    msg = (
        MessageSegment.image(info.cover_url)
        + MessageSegment.text(f"标题：{info.title}\nUP主：{info.author}\n\n{summary}")
    )
    await summary_matcher.finish(msg)
