"""消息采集器 — fire-and-forget 写入数据库，不影响主链路"""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from sqlalchemy.exc import IntegrityError

from src.models.message import GroupMessage
from src.services.database import get_db_session

collector = on_message(priority=99, block=False)


@collector.handle()
async def collect_message(event: GroupMessageEvent) -> None:
    # 过滤 bot 自身消息
    if event.user_id == event.self_id:
        return

    try:
        async with get_db_session() as session:
            msg = GroupMessage(
                group_id=event.group_id,
                user_id=event.user_id,
                plain_text=event.get_plaintext(),
                raw_message=event.raw_message,
                timestamp=event.time,
                message_id=event.message_id,
            )
            session.add(msg)
    except IntegrityError:
        # 重复 message_id（例如重放），静默忽略
        pass
    except Exception:
        # 其余数据库异常也不影响消息处理主链路
        pass
