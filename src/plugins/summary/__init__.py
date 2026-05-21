from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="每日群聊总结",
    description="群聊总结：热词排行、活跃榜、潜水提醒",
    usage="@bot 今日总结 手动触发",
)

from . import matchers
from . import scheduler

scheduler.register()
