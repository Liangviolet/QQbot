# QQ 多功能 Bot

基于 NoneBot2 + NapCatQQ 的 QQ 群多功能机器人，支持 B站解析、智能问答、群友画像、每日总结等功能。

## 功能一览

| 功能 | 触发方式 | 说明 |
|------|---------|------|
| 🎬 **B站视频解析** | 发送 `BV号` | 自动识别 BV 号并回复视频卡片（标题、UP主、封面） |
| 🤖 **AI 摘要** | `@bot 总结` | 对最近发送的 BV 视频生成 AI 摘要 |
| 💬 **智能问答** | `@bot <问题>` | 知识库匹配优先 + LLM 兜底回答 |
| 📚 **知识库管理** | `@bot kb add/list/del` | 管理员管理问答知识库 |
| 👤 **群友画像** | `@bot 看看@某人` | 发言统计、兴趣标签、关系网络 |
| 📊 **每日总结** | `@bot 今日总结` | 热词排行、活跃榜、潜水提醒 |
| 🗣️ **主动聊天** | 自动触发 | 在群聊中主动参与讨论、毒舌吐槽 |

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
- OpenAI 兼容 API Key（用于 AI 功能）

## 快速开始

### 1. 克隆项目

```bash
git clone <repo-url>
cd QQBot
```

### 2. 配置 NapCatQQ

NapCatQQ 已预置在 `NapCatQQ/` 目录中，配置文件位于 `NapCatQQ/config/`。

**启动 NapCatQQ：**

使用管理员身份运行 `go.bat`：

```batch
go.bat
```

该脚本会自动：
- 关闭旧版 QQ 和 NapCat 进程
- 加载 NapCatQQ 环境变量
- 启动 QQNT + NapCatQQ 注入

首次启动需扫描二维码登录 QQ 账号。

**Web 管理面板：**

NapCatQQ 自带 Web 管理面板，启动后访问：

```
http://localhost:6099
```

登录 Token 可在 `NapCatQQ/config/webui.json` 中查看。

### 3. 配置机器人

复制环境变量模板并编辑：

```bash
cp .env.example .env
```

编辑 `.env`，填入必要的密钥：

```env
# LLM API 密钥
OPENAI_API_KEY=sk-your-key-here

# Bot QQ 账号
BOT_QQ_ACCOUNT=3810708266
```

根据需要编辑 `config.yml` 调整插件配置：

```yaml
# config.yml 主要配置项
bot:
  persona:
    name: "毒舌吐槽君"     # 机器人名字
    reply_tone: "friendly"  # friendly | concise | formal

llm:
  provider: "openai"
  model: "gpt-4o-mini"
```

### 4. 安装依赖并启动机器人

```bash
# 创建虚拟环境（推荐）
python -m venv .venv

# 激活虚拟环境
.venv\Scripts\activate    # Windows
source .venv/bin/activate  # Linux/macOS

# 安装依赖
pip install -r requirements.txt

# 启动机器人
python bot.py
```

或直接使用 `start_bot.bat`（Windows）：

```batch
start_bot.bat
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
Bot 3810708266 connected
```

NapCatQQ 的 Web 管理面板中也可查看连接状态。

## 功能详情

### 🎬 B站视频解析

群内发送包含 BV 号的消息即可自动触发：

```
BV19jL46gEzQ
```

机器人会回复视频信息和封面图片。支持同时识别多条 BV 号（默认最多 3 条）。

### 🤖 AI 摘要

先发送 BV 号，再 `@bot 总结`：

```
@bot 总结
```

机器人会使用 LLM 生成该视频的摘要。

### 💬 智能问答

`@bot` + 问题即可触发问答：

```
@bot 今天天气怎么样？
```

问答流程：知识库匹配 → LLM 兜底回答。

### 📚 知识库管理（管理员）

```
@bot kb add 什么是反向代理 | 反向代理是一种服务器...
@bot kb list
@bot kb del 1
```

### 👤 群友画像

```
@bot 看看@张三
```

生成发言统计、兴趣标签、关系网络。

### 📊 每日总结

```
@bot 今日总结
```

**自动推送**（默认关闭）：可通过 `config.yml` 中 `plugins.summary.enabled` 开启定时推送：

```yaml
plugins:
  summary:
    enabled: true
    cron: "0 22 * * *"    # 每晚 22:00
    timezone: "Asia/Shanghai"
```

### 🗣️ 主动聊天

机器人会自动判断是否参与群聊讨论（默认开启）。

- 知识库匹配度高于 85 时自动回复
- AI 判断消息是否值得参与
- 同一群聊最少间隔 30 秒，避免刷屏

修改 `config.yml` 中的 `reply_tone` 可调整回答风格。

## 项目结构

```
QQBot/
├── bot.py                         # 入口文件
├── config.yml                     # 主配置文件
├── .env                           # 环境变量（密钥）
├── pyproject.toml                 # 项目元数据
├── NapCatQQ/                      # NapCatQQ 协议端
│   └── config/
│       ├── webui.json             # Web 面板配置
│       └── onebot11_3810708266.json  # OneBot 连接配置
├── src/
│   ├── config.py                  # Pydantic 配置模型
│   ├── models/                    # 数据库模型
│   ├── plugins/
│   │   ├── bilibili/             # B站解析插件
│   │   ├── profile/              # 群友画像插件
│   │   ├── qa/                   # 智能问答插件
│   │   └── summary/              # 每日总结插件
│   └── services/
│       ├── llm_client.py         # LLM API 客户端
│       ├── llm_router.py         # Prompt 组装与降级
│       ├── database.py           # 数据库会话管理
│       └── cache.py              # TTL 缓存
├── data/                          # 运行时数据
│   ├── bot.db                     # SQLite 数据库
│   └── knowledge_base.yml         # 知识库文件
├── tests/                         # 测试
├── go.bat                         # NapCatQQ 启动脚本（管理员）
└── start_bot.bat                  # 机器人启动脚本
```

## 常见问题

**Q: BV 号发到群里没反应？**

A: 检查是否开启了多个机器人实例，WebSocket 连接是否正常（终端日志应显示 `Bot xxx connected`）。

**Q: LLM 回复不可用？**

A: 检查 `.env` 中的 API Key 是否正确配置，以及 API 端点是否可达。

**Q: 如何更改人设？**

A: 修改 `config.yml` 中的 `bot.persona` 配置项，重启机器人生效。

## License

MIT
