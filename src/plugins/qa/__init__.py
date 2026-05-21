from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="智能问答",
    description="知识库优先 + LLM 兜底的智能问答",
    usage="@bot <问题>",
)

from . import matchers
