# QQ 多功能 Bot

基于 NoneBot2 + NapCatQQ 的 QQ 群多功能机器人，支持 B站解析、智能问答、群友画像、每日总结、主动聊天等功能。

## 功能一览

| 功能 | 触发方式 | 说明 |
|------|---------|------|
| 🎬 **B站视频解析** | 发送 `BV号` / `av号` / 视频链接 / `b23.tv` 短链 | 自动识别并回复视频卡片（标题、UP主、封面、播放量、时长） |
| 🤖 **AI 摘要** | `@bot 总结` | 对最近发送的 BV 视频生成 AI 摘要 |
| 💬 **智能问答** | `@bot <问题>` | 知识库匹配优先 + LLM 兜底回答 |
| 📚 **知识库管理** | `@bot kb add/list/del` | 管理员管理问答知识库 |
| 👤 **群友画像** | `@bot 看看` / `@bot 看看 @某人` | 发言统计、兴趣标签、互动关系（显示群昵称） |
| 📊 **每日总结** | `@bot 今日总结` | 热词排行、活跃榜、潜水提醒 |
| 🗣️ **主动聊天** | 自动触发（无需 @） | 在群聊中主动参与讨论、毒舌吐槽 |
| ℹ️ **自我介绍** | `@bot 看看`（不 @ 任何人） | 机器人用当前人设介绍自己 |

## 完整命令列表

### 智能问答
```
@bot <任意问题>          → 知识库匹配 → LLM 兜底回复
@bot                     → 空 @，机器人吐槽回应
```

### B站解析
```
BV19jL46gEzQ             → BV号自动解析
av170001                 → av号自动解析
https://www.bilibili.com/video/BV19jL46gEzQ  → 完整链接解析
b23.tv/xxxxx             → 短链解析
@bot 总结                → 对最近解析的视频生成 AI 摘要
```

### 群友画像
```
@bot 看看                → 机器人自我介绍
@bot 看看 @自己          → 查看自己的群聊画像
@bot 看看 @张三          → 查看张三的群聊画像
```
画像内容：发言总数、日均发言、活跃时段、兴趣标签、互动关系。

### 每日总结
```
@bot 今日总结            → 手动触发当日总结
```
内容包括：热词 TOP 5、发言活跃榜 TOP 3、潜水提醒。

### 知识库管理（仅管理员）
```
@bot kb list             → 列出所有知识库条目
@bot kb add 问题 | 答案   → 添加知识库条目
@bot kb del <id>         → 删除指定条目
```

### 主动聊天
机器人会自动判断是否参与群聊讨论，无需 @ 触发。
- 知识库匹配度高于 85 时自动回复
- AI 判断消息是否值得参与
- 同一群聊最少间隔 30 秒（可配置）
- 可在 `config.yml` 中关闭：`proactive_chat.enabled: false`

## 实际用例

```
# B站解析
用户: BV19jL46gEzQ
bot:  [封面图]
      标题：xxx | UP主：xxx | 播放：123,456 | 时长：3:45

用户: @bot 总结
bot:  该视频介绍了 xxx ...

# 群友画像
用户: @bot 看看 @小明
bot:  📋 小明的群聊画像
      ────────────
      📊 发言统计
      总发言：233 条 | 日均：14.5 条
      最活跃时段：22:00-0:00 点
      🏷 兴趣标签
      #游戏 #编程 #动漫
      🔗 互动关系
      与 小红 互动 42 次

# 每日总结
用户: @bot 今日总结
bot:  📊 今日群聊总结
      热词 TOP 3：原神(12次)、工作(8次)、吃饭(6次)
      发言 TOP 3：小明(42条)、小红(35条)、大白(28条)
      潜水提醒：老张今天还没说话哦

# 知识库
用户: @bot kb add 今天周几 | 今天是周五！
bot:  已添加知识库 #2
```

## 架构

```
NapCatQQ (QQ 协议端) ──WebSocket──> NoneBot2 (机器人框架) ──> 插件
```

- **NapCatQQ**: 基于 NTQQ 的轻量级无头框架，提供 OneBot V11 标准接口
- **NoneBot2**: 异步 Python 机器人框架
- **OneBot V11**: NapCatQQ 与 NoneBot 之间的通信协议（反向 WebSocket）

## 环境要求

- Python 3.12+
- Node.js 20+（NapCatQQ 依赖）
- QQNT（NapCatQQ 注入目标）
- API Key（DeepSeek / OpenAI / Anthropic）

## 快速开始（从零部署）

以下是从新机器完整部署的步骤。

### 1. 克隆项目

```bash
git clone <repo-url>
cd QQBot
```

### 2. 安装 NapCatQQ（QQ 协议端）

NapCatQQ 需要单独下载，不包含在 git 仓库中。

**下载 NapCatQQ：**

- 访问 [NapCatQQ Releases](https://github.com/NapNeko/NapCatQQ/releases)
- 下载最新版本的 `NapCat.Shell.zip`
- 将压缩包解压到项目根目录的 `NapCatQQ/` 文件夹中

或者使用命令行：

```bash
# 创建 NapCatQQ 目录并下载（以 v9.x 为例，请查看最新版本）
mkdir NapCatQQ
cd NapCatQQ
# 下载 NapCat.Shell.zip 并解压
```

**配置 NapCatQQ：**

配置文件位于 `NapCatQQ/config/`，关键配置：

1. `onebot11_<bot-qq>.json` — OneBot 连接配置（反向 WebSocket 地址）
2. `webui.json` — Web 管理面板登录 Token

**启动 NapCatQQ：**

```bash
cd NapCatQQ
napcat.bat
```

首次启动需扫描二维码登录 QQ 账号。

> 详细部署文档请参考 [NapCatQQ 官方文档](https://napneko.github.io/)

**配置 NapCatQQ 连接到机器人：**

确保 `NapCatQQ/config/onebot11_<bot-qq>.json` 中的反向 WebSocket 地址指向机器人监听端口（默认 `ws://127.0.0.1:8080/onebot/v11/ws/`）：

```json
{
  "ws_reverse_servers": [{
    "name": "QQBot",
    "url": "ws://127.0.0.1:8080/onebot/v11/ws/",
    "reconnect_interval": 3000
  }]
}
```

**Web 管理面板：**

NapCatQQ 启动后访问 `http://localhost:6099`，Token 在 `NapCatQQ/config/webui.json` 中查看。

### 3. 配置机器人

复制环境变量模板并编辑：

```bash
cp .env.example .env
```

编辑 `.env`，填入必要的密钥：

```env
# LLM API 密钥（DeepSeek / OpenAI 等，至少配置一个）
OPENAI_API_KEY=sk-your-api-key-here

# Bot QQ 账号
BOT_QQ_ACCOUNT=1234567890
```

编辑 `config.yml` 调整机器人配置（可选）：

```yaml
bot:
  persona:
    name: "毒舌美少女"       # 人设名称
    reply_tone: "friendly"    # friendly | concise | formal

llm:
  provider: "openai"
  model: "deepseek-v4-flash"
  base_url: "https://api.deepseek.com"
```

### 4. 安装依赖并启动机器人

```bash
# 1. 创建虚拟环境（推荐）
python -m venv .venv

# 2. 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. 安装依赖（从 pyproject.toml）
pip install -e .

# 4. 启动机器人
python bot.py
```

### 5. 验证连接

启动后终端应显示：

```
NoneBot is initializing...
Succeeded to load plugin "bilibili"
Succeeded to load plugin "qa"
Succeeded to load plugin "profile"
Succeeded to load plugin "summary"
Running NoneBot...
Uvicorn running on http://127.0.0.1:8080
Bot <your-bot-qq> connected
```

NapCatQQ 的 Web 管理面板中也可查看连接状态。

## 配置参考

### config.yml 主要配置项

```yaml
# 人设
bot:
  persona:
    name: "毒舌美少女"       # 机器人人设名称
    reply_tone: "friendly"    # 回复语气

# LLM
llm:
  provider: "openai"          # openai / anthropic
  model: "deepseek-v4-flash"  # 模型名
  base_url: "https://api.deepseek.com"  # API 地址
  temperature: 0.7             # 生成温度

# 插件开关
plugins:
  qa:
    enabled: true              # 智能问答
  bilibili:
    enabled: true              # B站解析
  summary:
    enabled: false             # 定时每日总结（手动命令不受影响）
  proactive_chat:
    enabled: true              # 主动聊天
    cooldown_seconds: 30       # 同一群聊发言冷却
  profile:
    enabled: true              # 群友画像
```

### .env 环境变量

```env
# LLM API 密钥（至少配置一个）
OPENAI_API_KEY=sk-your-openai-api-key
# ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key

# Bot QQ 账号
BOT_QQ_ACCOUNT=1234567890
```

## 项目结构

```
QQBot/
├── bot.py                         # 入口文件
├── config.yml                     # 主配置文件
├── .env                           # 环境变量（密钥，已 gitignore）
├── .env.example                   # 环境变量模板
├── pyproject.toml                 # 项目元数据
├── NapCatQQ/                      # NapCatQQ 协议端（需自行下载）
│   └── config/                    # 连接配置、Web 面板 Token
│       ├── webui.json             # Web 面板配置
│       └── onebot11_<qq>.json     # OneBot 连接配置
├── src/
│   ├── config.py                  # Pydantic 配置模型
│   ├── models/                    # 数据库模型
│   │   ├── message.py             # 群消息模型
│   │   └── summary.py             # 总结记录模型
│   ├── plugins/
│   │   ├── bilibili/             # B站解析插件
│   │   │   ├── matchers.py       # BV检测 + 总结命令
│   │   │   ├── parser.py         # BV/av/URL/b23 解析
│   │   │   └── renderer.py       # 消息格式化
│   │   ├── profile/              # 群友画像插件
│   │   │   ├── matchers.py       # 画像查询命令
│   │   │   ├── analyzer.py       # 统计、标签、关系图
│   │   │   ├── collector.py      # 消息采集入库
│   │   │   └── models.py         # 画像数据模型
│   │   ├── qa/                   # 智能问答插件
│   │   │   ├── matchers.py       # @bot 处理 + 主动聊天
│   │   │   ├── router.py         # 知识库 → LLM 路由
│   │   │   └── knowledge.py      # YAML 知识库引擎
│   │   └── summary/              # 每日总结插件
│   │       ├── matchers.py       # @bot 今日总结命令
│   │       ├── generator.py      # 热词、排行、潜水分析
│   │       └── scheduler.py      # APScheduler 定时任务
│   └── services/
│       ├── llm_client.py         # LLM API 客户端
│       ├── llm_router.py         # Prompt 组装与降级
│       ├── database.py           # 数据库会话管理
│       └── cache.py              # TTL 缓存
├── data/
│   ├── bot.db                    # SQLite 数据库
│   └── knowledge_base.yml        # 知识库文件
└── tests/
    ├── test_bilibili/
    ├── test_profile/
    ├── test_qa/
    ├── test_summary/
    ├── test_cache.py
    └── test_database.py
```

## 常见问题

**Q: 发 BV 号到群里没反应？**
A: 检查 WebSocket 连接是否正常（终端日志应显示 `Bot xxx connected`）。B站 API 可能有频率限制，稍等重试。

**Q: @bot 没反应？**
A: 检查以下几点：
   - `.env` 中的 API Key 是否正确配置，API 端点是否可达
   - 是否已激活虚拟环境
   - NapCatQQ 是否已成功启动并连接（终端应显示 `Bot xxx connected`）
   - 查看 `logs/bot.log` 中的错误日志

**Q: 数据库是怎么创建的？需要手动初始化吗？**
A: 不需要。首次启动机器人时，`bot.py` 会自动调用 `init_db()` 创建 SQLite 数据库和所有表（`data/bot.db`）。如果遇到 "no such table" 错误，检查是否启动了正确的入口文件（`python bot.py`，不是 `python -m nonebot`）。

**Q: 如何更改人设？**
A: 修改 `config.yml` 中的 `bot.persona.name` 和 `reply_tone`，重启机器人生效。

**Q: 机器人不说话但日志没报错？**
A: 检查 `config.yml` 中对应插件是否 `enabled: true`。检查 `proactive_chat.enabled` 是否开启。

**Q: 群友画像显示"未找到该群友"？**
A: 对方需要在本群发过至少 `min_messages_for_profile`（默认 10）条消息才能生成画像。

## License

MIT
