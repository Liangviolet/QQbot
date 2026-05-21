"""Bilibili 测试共享配置 — 初始化 NoneBot 以便 matchers 导入"""

import nonebot

# 初始化 NoneBot，使 on_command / get_driver 等 API 在测试中可用
nonebot.init()
