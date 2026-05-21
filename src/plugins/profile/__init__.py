from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="群友画像",
    description="发言统计、兴趣标签、关系网络",
    usage="@bot 看看<@用户>的画像",
)

from . import collector
from . import matchers
