from nonebot.adapters.onebot.v11 import Message, MessageSegment

from src.plugins.bilibili.parser import VideoInfo, format_duration


def format_video_card(info: VideoInfo) -> Message:
    """将 VideoInfo 格式化为包含封面图和文本的 OneBot Message"""
    duration_str = format_duration(info.duration)
    text = (
        f"标题：{info.title}\n"
        f"UP主：{info.author}\n"
        f"播放：{info.views:,}\n"
        f"时长：{duration_str}"
    )
    return Message(
        MessageSegment.image(info.cover_url)
        + MessageSegment.text(text)
    )


def format_multi_video_cards(infos: list[VideoInfo]) -> Message:
    """合并多个 BV 号的结果为一条消息"""
    msg = Message()
    for i, info in enumerate(infos):
        if i > 0:
            msg += MessageSegment.text("\n---\n")
        msg += format_video_card(info)
    return msg


def format_bv_limit_warning(count: int, limit: int = 3) -> str:
    return f"检测到{count}个BV号，仅展示前{limit}个"
