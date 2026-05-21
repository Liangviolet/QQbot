"""手动触发群聊总结命令"""

from datetime import datetime

from nonebot import on_message, logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.rule import to_me

from src.config import load_config
from src.services.llm_client import create_llm_client

from .generator import generate_summary

summary_cmd = on_message(rule=to_me(), priority=8, block=False)


@summary_cmd.handle()
async def handle_summary_cmd(event: GroupMessageEvent):
    text = event.get_plaintext().strip()
    if text != "今日总结":
        return

    config = load_config()
    group_id = event.group_id

    # 构造日期
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(config.plugins.summary.timezone)
    except Exception:
        tz = None
    now = datetime.now(tz) if tz else datetime.now()
    date_dt = datetime(now.year, now.month, now.day, tzinfo=tz)

    # 构造 LLM 客户端（可选）
    llm_client = None
    persona_config = None
    try:
        llm_config = config.llm
        api_key = getattr(config, f"{llm_config.provider}_api_key", None) or ""
        llm_client = create_llm_client({
            "provider": llm_config.provider,
            "api_key": api_key,
            "base_url": llm_config.base_url,
            "model": llm_config.model,
        })
        persona_config = {
            "name": config.bot.persona.name,
            "reply_tone": config.bot.persona.reply_tone,
        }
    except Exception:
        pass  # LLM 不可用时用纯模板

    summary = await generate_summary(
        group_id,
        date_dt,
        llm_client=llm_client,
        persona_config=persona_config,
    )

    await summary_cmd.finish(summary)
