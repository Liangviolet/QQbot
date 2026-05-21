from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="B站解析",
    description="自动识别 BV 号并回复视频信息卡片",
    usage="发送含 BV 号的消息即可自动触发",
)

from . import matchers
