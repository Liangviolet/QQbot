"""QQ 多功能 Bot — 入口文件"""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)


@driver.on_startup
async def _init_database():
    from src.services.database import init_db
    await init_db()


nonebot.load_plugins("src/plugins")

if __name__ == "__main__":
    nonebot.run()
