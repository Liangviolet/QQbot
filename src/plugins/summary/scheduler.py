"""U6 每日群聊总结调度器 — APScheduler cron 定时任务

所有 NoneBot 依赖的模块均采用延迟加载（在 register() 中），
避免在测试环境或 NoneBot 未初始化时导入报错。
"""

from datetime import datetime

from sqlalchemy import select, distinct

from src.config import load_config
from src.models.message import GroupMessage
from src.services.database import get_db_session

from .generator import generate_summary, get_last_summary_date, set_last_summary_date


def register() -> None:
    """注册每日群聊总结 cron job。

    在 driver 启动时读取配置并添加到 APScheduler。
    此函数可在 NoneBot 未初始化时安全调用（静默跳过）。
    """
    try:
        from nonebot import get_driver
        driver = get_driver()
    except ValueError:
        return  # NoneBot 尚未初始化（测试环境等）

    @driver.on_startup
    async def _register_summary_job() -> None:
        try:
            from nonebot import require
            require("nonebot_plugin_apscheduler")
            from nonebot_plugin_apscheduler import scheduler  # noqa: E402
        except Exception:
            return  # APScheduler 插件未安装

        config = load_config()
        if not config.plugins.summary.enabled:
            return

        cron_kwargs = _parse_cron(config.plugins.summary.cron)
        scheduler.add_job(
            send_daily_summary,
            "cron",
            id="daily_summary_job",
            replace_existing=True,
            **cron_kwargs,
            timezone=config.plugins.summary.timezone,
        )


def _parse_cron(expression: str) -> dict:
    """将标准 5 段 cron 表达式解析为 APScheduler cron 参数字典。"""
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError(f"无效的 cron 表达式: {expression}")
    keys = ["minute", "hour", "day", "month", "day_of_week"]
    result = {}
    for key, val in zip(keys, parts):
        try:
            result[key] = int(val) if val != "*" else "*"
        except ValueError:
            result[key] = val
    return result


async def send_daily_summary() -> None:
    """发送每日群聊总结给所有有消息记录的群组。"""
    try:
        from nonebot import get_bot
        bot = get_bot()
    except ValueError:
        return  # bot 尚未就绪

    config = load_config()

    # 构造当前日期（考虑时区）
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(config.plugins.summary.timezone)
    except Exception:
        tz = None

    now = datetime.now(tz) if tz else datetime.now()
    today_str = now.date().isoformat()
    date_dt = datetime(now.year, now.month, now.day, tzinfo=tz)

    # 获取所有有消息记录的群组
    async with get_db_session() as session:
        result = await session.execute(
            select(distinct(GroupMessage.group_id))
        )
        group_ids = [row[0] for row in result]

    for group_id in group_ids:
        last_date = await get_last_summary_date(group_id)
        if last_date == today_str:
            continue  # 当天已发送，跳过

        try:
            summary = await generate_summary(group_id, date_dt)
        except Exception:
            continue  # 生成失败跳过（如数据库异常）

        try:
            await bot.send_group_msg(group_id=group_id, message=summary)
        except Exception:
            continue  # 发送失败跳过（如 bot 已退出群）

        try:
            await set_last_summary_date(group_id, today_str)
        except Exception:
            continue  # 记录失败仅影响去重，下次 cron 可能重复发送
