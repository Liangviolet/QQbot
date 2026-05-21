---
title: feat: QQ 多功能 Bot 开发
type: feat
status: active
date: 2026-05-21
origin: docs/brainstorms/2026-05-21-qq-bot-requirements.md
---

# feat: QQ 多功能 Bot 开发

## Summary

基于 NapCatQQ + NoneBot2 + OneBot v11 + SQLite 构建一个绿色区域（greenfield）QQ bot。插件化架构，四个功能插件分别负责智能问答（知识库优先 + LLM 兜底）、B站 BV 号解析（视频信息 + AI 摘要）、每日群聊总结（APScheduler 定时触发）和群友画像（发言统计 + 兴趣标签 + 关系网络）。所有配置通过 YAML + .env 管理，无 Web 后台。

---

## Problem Frame

现有关键词匹配 bot 过于僵硬，无法理解自然语言变体，也不支持 B站内容解析或群友数据分析。需要构建一个「懂人话」的智能 bot：知识库覆盖常见问题，LLM 兜底处理长尾提问，同时自动化群内高频场景（BV 识别、群聊回顾、成员画像）。本计划基于 `docs/brainstorms/2026-05-21-qq-bot-requirements.md` 中的所有 15 条需求和 4 个关键流程。

---

## Requirements

**智能问答**
- R1. bot 被 @ 提及时，提取问题文本，先在知识库中做语义/关键词匹配，匹配命中则返回预设回答
- R2. 知识库无匹配时，将问题发送至 LLM 生成回答，回答携带简短免责（如 "AI 生成，仅供参考"）
- R3. 知识库支持主人 (A2) 通过指令添加、修改、删除、列出 Q&A 条目

**B站解析**
- R4. bot 自动检测群消息中的 Bilibili BV 号，无需 @bot 即可触发
- R5. 识别后回复视频信息卡片，包含：标题、UP 主、播放量、封面图、视频时长
- R6. 支持通过指令请求该视频的 AI 内容摘要（如 "@bot 总结一下这个视频"）

**群友画像**
- R7. bot 持续记录群内消息，按用户维度统计：总发言数、活跃时段分布、高频词汇
- R8. 基于聊天内容自动推断群友兴趣标签（如游戏、动漫、编程等），支持人工修正
- R9. 分析群友间的互动关系：@ 频率、互相回复次数，构建简化的关系强度图
- R10. 支持按指令查询指定群友的画像报告，报告包含 R7-R9 的数据
- R11. 画像数据仅来源于该群内的公开聊天，不爬取群友其他平台信息

**行为模式**
- R12. bot 有两种默认主动行为：BV 号自动识别（始终开启）和每日群聊总结（默认开启，可关闭）
- R13. 每日群聊总结内容包含：当日热门话题关键词 TOP 5、发言活跃榜、新人/潜水提醒
- R14. 除 R12 所列之外的可选主动行为均为独立开关，默认关闭，由 A2 手动启用
- R15. bot 具有可配置的基础人设（称呼风格、回复语气），由 A2 通过配置文件设定

**Origin actors:** A1 (群友 — 通过 @bot 提问或发消息触发 bot 功能), A2 (bot 主人 — 配置知识库、管理主动行为开关、调整 bot 人设参数)

**Origin flows:** F1 (智能问答), F2 (B站 BV 号解析), F3 (每日群聊总结), F4 (群友画像查询)

**Origin acceptance examples:** AE1 (KB 命中, covers R1-R2), AE2 (LLM 兜底, covers R1-R2), AE3 (BV 自动识别, covers R4-R5), AE4 (无 @ 不响应, covers R1), AE5 (画像查询, covers R10), AE6 (每日总结, covers R12-R13)

---

## Scope Boundaries

- 不包含 Web 管理后台 —— 配置通过 YAML 文件完成
- 不包含 b23.tv 短链接解析 —— v1 仅处理标准 BV 号正则 (BV[1-9A-HJ-NP-Za-km-z]{10})
- 不包含 B站内容订阅追踪（UP 主动态、番剧更新提醒等）
- 不含群友画像的导出和可视化图表 —— 纯文本报告
- 不含全自动 AI 主动插话 —— 主动行为限定为 BV 识别 + 每日总结
- 不含多用户权限体系 —— A2（主人）通过 QQ 号在配置中指定，单一管理员

### Deferred to Follow-Up Work

- b23.tv 短链解析：需额外 HTTP 重定向处理，v2 添加
- 群友画像可视化图表：可后续集成图表生成库
- 多群管理面板：若扩展到 3+ 群时重新评估
- 向量嵌入语义匹配升级：当知识库超过 ~200 条时替换 thefuzz

---

## Context & Research

### Relevant Code and Patterns

绿色区域项目，无现有代码可参考。以下为调研确定的架构模式：

- **NoneBot2 插件模式**: 每个功能域一个子包 (`src/plugins/{qa,bilibili,profile,summary}/`)，含 `matchers.py`、业务逻辑模块、`__init__.py` 注册元数据
- **共享服务层**: `src/services/` 提供跨插件复用的 LLM 客户端、数据库会话、缓存
- **Dependency Injection**: 使用 NoneBot2 的 `Depends()` 注入数据库会话和 LLM 客户端到 matcher handler 中
- **OneBot v11 事件**: 群消息通过 `GroupMessageEvent` 获取，@ 检测用 `event.is_tome()`，纯文本通过 `event.get_plaintext()` 提取
- **Matcher 优先级**: 问答用 `priority=10, block=True`（命中即止），BV 检测用 `priority=90, block=False`（不阻止其他 matcher）。BV 检测必须过滤 `event.user_id == event.self_id` 防止自触发无限循环

### Institutional Learnings

无现有 `docs/solutions/` 条目。本计划完成后可产出 learnings。

### External References

- NoneBot2 官方文档: `https://nonebot.dev/`
- OneBot v11 协议规范: `https://github.com/botuniverse/onebot-11`
- B站 API 合集: `SocialSisterYi/bilibili-API-collect` (GitHub)
- `bilibili-api-python` 库: `Nemo2011/bilibili-api` (GitHub)
- NapCatQQ: `NapNeko/NapCatQQ` (GitHub)
- nonebug (NoneBot2 测试框架): `nonebot/nonebug` (GitHub)
- nonebot-plugin-apscheduler: `nonebot/plugin-apscheduler` (GitHub)

---

## Key Technical Decisions

- **NapCatQQ + OneBot v11 协议端**: 2025-2026 社区首选，替代已停更的 go-cqhttp。提供 WebSocket 反向连接模式，内置重连和 WebUI 管理
- **NoneBot2 而非裸 OneBot 客户端**: 提供插件化架构、依赖注入、测试工具 (nonebug)、丰富的社区插件生态。纯异步模型匹配 I/O 密集型 bot 工作负载
- **SQLite + aiosqlite + SQLAlchemy async**: 个人小群场景下零运维开销，WAL 模式支持并发读写。SQLAlchemy 抽象层保留未来迁移到 PostgreSQL 的可能。原始消息 90 天保留，聚合统计永久保留
- **两阶段 KB 匹配 (关键词精确 → thefuzz 模糊) 而非向量嵌入**: 个人知识库规模小 (<200 条)，thefuzz 的 Levenshtein 距离对于中文短文本问法变体足够有效，免去 embedding 模型和向量数据库的额外依赖
- **LLM 抽象层 (ABC 策略模式)**: 隔离 OpenAI/Anthropic/本地模型差异，方便切换 provider 和 mock 测试。每个 API 调用携带指数退避重试 (tenacity, max 3 次)
- **R6 会话上下文 (BV→AI 摘要)**: 每组维护最近解析 BV 号的 5 分钟 TTL 缓存。用户 @bot 请求摘要时优先检查缓存；过期则引导用户重新发送 BV 号
- **自消息过滤**: 所有消息 handler 在入口处过滤 `event.user_id == event.self_id`，防止 bot 自己的 BV 卡片回复触发 BV 检测无限循环。每日总结也需过滤 bot 自身的消息
- **LLM 降级策略**: F2-R6 的 AI 摘要返回 "AI 摘要暂时不可用"；F3 每日总结回退到纯统计模板（无自然语言润色）；F4 兴趣标签回退到关键词规则匹配（无 LLM 推理）。统一封装在 LLM 客户端层的 `LLMUnavailableException` 中

---

## Open Questions

### Resolved During Planning

- **QQ bot 协议端选型**: 选用 NapCatQQ + OneBot v11 + 反向 WebSocket。理由见 Key Technical Decisions
- **消息存储方案**: SQLite + aiosqlite + SQLAlchemy async。理由见 Key Technical Decisions
- **LLM 模型选型**: 默认 gpt-4o-mini (OpenAI 兼容 API)，通过 `config.yml` 可切换为 anthropic 或任何 OpenAI 兼容端点（如 DeepSeek）。个人使用场景月费预计 <$5
- **BV 号正则模式**: `\b(BV[1-9A-HJ-NP-Za-km-z]{10})\b`，仅匹配大写 BV 前缀的标准 12 位 BV 号。小写 bv 不触发（避免误报）。单消息最多处理 3 个 BV 号，合并为一条回复
- **主动行为边界**: BV 自动识别（始终开启）+ 每日群聊总结（默认开启，可关闭）。已反映在 R12-R14 中
- **R6 会话上下文**: 每组最近 BV 缓存，5 分钟 TTL。已反映在 Key Technical Decisions 中
- **每日总结去重**: 数据库记录 `last_summary_date` per group，发送前检查，跳过已发送日
- **用户画像名解析**: 必须 @mention 目标用户（OneBot v11 `at` segment）以精确获取 user_id。纯文本名称尝试模糊匹配，多个候选时列出提示
- **非文本消息处理**: v1 忽略图片/语音/表情包的语义内容。表情包计入发言数统计但不参与关键词/标签提取
- **意图优先级**: @bot + BV 共存时，BV 卡片先发（F2, block=False），问答随后处理（F1, block=True）
- **画像数据生命周期**: 已退群成员数据保留但不可查询；重新入群后历史数据恢复可查

### Deferred to Implementation

- [Affects R1] `event.is_tome()` 在不同 OneBot 客户端实现中的精确行为差异 —— 需在真实环境验证
- [Affects R7] 消息记录在高频群（日数千条）下的 SQLite WAL 写入压力 —— 需实测确认，必要时引入批量写入
- [Affects R8] 兴趣标签词表的初始填充和持续更新策略 —— 初始手工配置 30-50 个关键词映射，后续根据实际聊天内容迭代
- [Affects R2] LLM API 的精确超时和重试参数 —— 需根据实际 API 延迟调优
- [Needs research] `bilibili-api-python` 库 vs 直接 HTTP 调用 —— 需要比较两者的 WBI 签名实现和异步支持。计划先用直接 HTTP + httpx，若 WBI 签名复杂度超预期再切换为 bilibili-api-python

---

## Output Structure

```
E:\QQbot\
├── bot.py                         # 入口：加载驱动、注册 OneBot V11 适配器、加载插件
├── pyproject.toml                  # PEP 621 项目元数据 + 依赖声明
├── config.yml                      # 应用配置（bot 人设、插件参数、LLM、数据库、日志）
├── .env                            # 密钥（API keys、QQ 账号）—— gitignore
├── .env.example                    # 配置模板（无真实值）
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── config.py                   # Pydantic 配置模型，加载 config.yml + .env
│   ├── plugins/
│   │   ├── __init__.py
│   │   ├── qa/
│   │   │   ├── __init__.py         # 插件元数据 + require 声明
│   │   │   ├── matchers.py         # on_message(to_me()) + KB 管理指令
│   │   │   ├── knowledge.py        # KnowledgeBase: 从 YAML 加载、搜索（关键词 → thefuzz）
│   │   │   └── router.py           # 问答路由：KB 匹配 → LLM 兜底 → 降级
│   │   ├── bilibili/
│   │   │   ├── __init__.py
│   │   │   ├── matchers.py         # on_message(BV regex) + on_command(summary)
│   │   │   ├── parser.py           # BV 正则提取、B站 API 调用、响应缓存
│   │   │   └── renderer.py         # 视频信息 → OneBot Message（封面图 + 文本卡片）
│   │   ├── profile/
│   │   │   ├── __init__.py
│   │   │   ├── collector.py        # 低优先级消息记录器（fire-and-forget）
│   │   │   ├── analyzer.py         # 统计计算、标签推断、关系图构建
│   │   │   ├── matchers.py         # on_message(to_me()) 画像查询
│   │   │   └── models.py           # 画像相关 dataclass
│   │   └── summary/
│   │       ├── __init__.py
│   │       ├── scheduler.py        # APScheduler cron 注册 + 去重检查
│   │       └── generator.py        # 热词聚合、发言排行、模板化格式化
│   ├── services/
│   │   ├── __init__.py
│   │   ├── database.py             # SQLAlchemy async engine + session factory + WAL 初始化
│   │   ├── llm_client.py           # LLMClient ABC + OpenAI/Anthropic 实现 + 重试逻辑
│   │   ├── llm_router.py           # prompt 组装、人设注入、降级处理
│   │   └── cache.py                # 内存 TTL 缓存（BV 上下文、LLM 响应）
│   ├── models/
│   │   ├── __init__.py
│   │   ├── message.py              # GroupMessage ORM 模型
│   │   └── base.py                 # SQLAlchemy declarative Base
│   └── utils/
│       ├── __init__.py
│       ├── text.py                  # jieba 分词、停用词过滤、文本清洗
│       ├── rate_limit.py            # 内存 token bucket 限流器
│       └── logging_config.py        # structlog 配置 + 文件轮转
├── data/
│   ├── knowledge_base.yml           # 可编辑 Q&A 条目
│   └── .gitkeep                     # bot.db 自动创建
├── tests/
│   ├── conftest.py                  # 共享 fixtures: 内存 SQLite、mock LLM 客户端、nonebug app
│   ├── test_qa/
│   │   ├── test_knowledge.py        # KB 搜索单元测试 (关键词/模糊/未命中)
│   │   └── test_matchers.py         # Q&A 集成测试 (KB命中/LLM兜底/空问题/无@不响应)
│   ├── test_bilibili/
│   │   ├── test_parser.py           # BV 正则提取单元测试 (单/多/无/去重/大小写/URL中)
│   │   └── test_matchers.py         # BV 集成测试 (API mock/缓存/多BV合并/自消息过滤)
│   ├── test_profile/
│   │   ├── test_analyzer.py         # 标签推断/关系图构建单元测试
│   │   └── test_matchers.py         # 画像查询集成测试 (正常/冷启动/用户不存在)
│   └── test_summary/
│       └── test_generator.py        # 热词聚合/排行/潜水检测/空日处理 单元测试
├── logs/
│   └── .gitkeep
└── docs/
    ├── brainstorms/
    │   └── 2026-05-21-qq-bot-requirements.md
    └── plans/
        └── 2026-05-21-001-feat-qq-multifunctional-bot-plan.md
```

---

## Implementation Units

### U1. 项目脚手架与基础设施

**Goal:** 搭建 NoneBot2 项目骨架，包括入口文件、配置加载、依赖声明、目录结构。确保 `nb run` 可启动并通过 OneBot v11 反向 WebSocket 接收 NapCatQQ 的消息。

**Requirements:** R12, R15 (配置骨架支撑所有后续功能)

**Dependencies:** None (绿色区域起点)

**Files:**
- Create: `bot.py`, `pyproject.toml`, `config.yml`, `.env.example`, `.gitignore`
- Create: `src/__init__.py`, `src/config.py`
- Create: `src/utils/__init__.py`, `src/utils/logging_config.py`
- Create: `data/.gitkeep`, `logs/.gitkeep`

**Approach:**
- `bot.py` 初始化 `nonebot.init()`，注册 `OnebotV11Adapter`，调用 `nonebot.load_plugins("src/plugins")`
- `.env` 通过 `pydantic-settings` 加载密钥（OPENAI_API_KEY, ANTHROPIC_API_KEY, BOT_QQ_ACCOUNT），`config.yml` 通过 Pydantic 加载所有运行参数
- config.yml 包含 bot 人设 (R15)、LLM provider/model/retry 参数、插件级开关和参数、数据库路径、日志级别
- `.gitignore` 排除 `.env`、`data/bot.db`、`logs/`、`__pycache__/`、`.venv/`
- `logging_config.py` 配置 structlog + RotatingFileHandler（10MB/7天轮转）

**Patterns to follow:**
- NoneBot2 官方快速入门项目结构
- pydantic-settings `.env` 自动加载模式

**Test scenarios:**
- Happy path: `python bot.py` 启动后日志显示 "OneBot V11 adapter registered"，WebSocket 监听就绪
- Edge case: 缺失 `.env` 文件时 bot 应以可理解的错误信息退出，而非静默崩溃
- Edge case: config.yml 中必填字段缺失时，Pydantic 验证应在启动时抛出清晰错误

**Verification:**
- bot 进程启动无报错，日志输出 adapter 注册成功
- 反向 WebSocket 端点可被 NapCatQQ 连接
- `nonebot.get_driver().config` 可读取到 config.yml 中的自定义配置项

---

### U2. 消息持久化存储

**Goal:** 创建 SQLite 数据库层，包含 GroupMessage ORM 模型和异步会话管理。所有后续插件依赖此层进行消息记录和查询。

**Requirements:** R7 (持续记录群消息), R8, R9, R11 (画像数据仅来源群内聊天), R13 (每日总结数据源)

**Dependencies:** U1 (数据库配置项)

**Files:**
- Create: `src/models/__init__.py`, `src/models/base.py`, `src/models/message.py`
- Create: `src/services/__init__.py`, `src/services/database.py`

**Approach:**
- SQLAlchemy async engine with `sqlite+aiosqlite:///data/bot.db`，connect_args 含 `check_same_thread: False`
- engine 首次连接时执行 `PRAGMA journal_mode=WAL` 和 `PRAGMA foreign_keys=ON`
- `GroupMessage` 模型字段：id (PK), group_id, user_id, plain_text (去 CQ 码纯文本), raw_message (完整 JSON), timestamp, message_id (QQ 消息 ID，UNIQUE 防重)
- 复合索引 `idx_group_time (group_id, timestamp)` 和 `idx_user_group (user_id, group_id)` 用于画像和总结的高频查询
- `get_db_session` 作为 NoneBot2 `Depends()` provider，自动 commit/rollback

**Patterns to follow:**
- SQLAlchemy 2.0 async ORM 声明式映射
- NoneBot2 startup/shutdown 钩子管理引擎生命周期

**Test scenarios:**
- Happy path: 插入一条 GroupMessage 后按 user_id + group_id 查询可正确返回
- Edge case: 相同 message_id 重复插入时应触发 unique constraint，session 正确处理
- Edge case: 并发插入（5 条消息同时到达）时 WAL 模式不产生锁冲突
- Error path: 数据库文件所在目录不可写时，引擎创建应抛出清晰异常

**Verification:**
- `data/bot.db` 文件自动创建，包含 `group_messages` 表和两条索引
- 插入 1000 条模拟消息后，按 group_id+时间范围查询耗时 <50ms

---

### U3. 共享服务层 (LLM 客户端 + HTTP 客户端 + 缓存)

**Goal:** 实现跨插件复用的核心服务：多 provider LLM 抽象客户端、内存 TTL 缓存、API 限流器。

**Requirements:** R2 (LLM 兜底回答), R6 (AI 视频摘要), R8 (标签推断可选 LLM 辅助), R13 (总结可选 LLM 润色)

**Dependencies:** U1 (config.yml 中的 LLM 配置)

**Files:**
- Create: `src/services/llm_client.py`, `src/services/llm_router.py`, `src/services/cache.py`
- Create: `src/utils/rate_limit.py`

**Approach:**
- `LLMClient` ABC 定义 `chat(system_prompt, user_message, max_tokens, temperature) → LLMResponse` 接口
- `OpenAIClient` 和 `AnthropicClient` 具体实现。通过 config.yml 的 `provider` 字段选择；`base_url` 可覆盖以支持 DeepSeek 等兼容 API
- 使用 `tenacity` 库实现指数退避重试：max 3 次, wait_exponential(min=1s, max=10s)
- `llm_router.py` 的 `generate_answer()` 封装了 persona 注入 + 重试 + 降级处理。当所有重试失败时抛出 `LLMUnavailableException`
- `cache.py` 实现泛型 `TTLCache[T]`：基于 dict + timestamp，支持 max_size 淘汰。用于 BV 视频信息缓存 (R5) 和 BV 上下文缓存 (R6)
- `rate_limit.py` 实现 token bucket 限流器：per (user_id, action) key，用于防止 LLM API 滥用

**Patterns to follow:**
- 策略模式 (ABC) 用于可替换的 LLM provider
- NoneBot2 `Depends()` provider 模式注入共享服务实例

**Test scenarios:**
- Happy path: mock OpenAI API 返回正常响应 → `generate_answer()` 返回内容 + tokens_used
- Error path: mock API 连续返回 500 → 三次重试后抛出 `LLMUnavailableException`
- Error path: mock API 超时 → 触发重试逻辑
- Edge case: TTL 缓存过期后访问 → 返回 None，不返回 stale 数据
- Edge case: rate limiter 连续请求超过限制 → 第 11 次请求返回 False

**Verification:**
- 使用 mock HTTP endpoint 验证重试逻辑的正确次数和间隔
- TTL 缓存项在过期时间后自动不可达
- rate limiter 桶在 period 过后自动清空

---

### U4. 智能问答插件

**Goal:** 实现 @bot 智能问答：知识库匹配优先 → LLM 兜底。同时支持主人通过指令管理知识库条目。

**Requirements:** R1, R2, R3, R15

**Dependencies:** U3 (LLM 客户端, 缓存)

**Files:**
- Create: `src/plugins/qa/__init__.py`, `src/plugins/qa/matchers.py`, `src/plugins/qa/knowledge.py`, `src/plugins/qa/router.py`
- Create: `data/knowledge_base.yml`
- Create: `tests/test_qa/test_knowledge.py`, `tests/test_qa/test_matchers.py`

**Approach:**
- `knowledge.py`: `KnowledgeBase` 类从 `data/knowledge_base.yml` 加载条目（YAML 格式：id, question, keywords[], answer）。搜索采用两阶段：① 关键词精确子串匹配（score=100，直接返回）；② thefuzz `partial_ratio` 模糊匹配（需 >= `match_threshold` 才命中）
- `matchers.py`: `on_message(rule=to_me(), priority=10, block=True)` 处理 @bot 消息。提取 `event.get_plaintext()` 去除非问题噪音后传给 router。额外注册 KB 管理指令（`kb add/list/del`），仅允许 `event.user_id` 在配置的 superusers 列表中执行 (R3)
- `router.py`: 调用 `KnowledgeBase.search()` → 命中则直接返回 → 未命中则调用 `llm_router.generate_answer()` → 追加 "AI 生成，仅供参考" 免责声明 → LLM 不可用时返回 "抱歉，AI 服务暂时不可用" 降级回复
- 对于仅有 @bot 但无有效提问的消息，返回简短引导 "在呢，有什么可以帮你的？"（R12 约束：被动响应但不死板）
- 人设 (R15) 通过 `llm_router` 的 system_prompt 参数注入，内容来自 config.yml 的 `bot.persona`

**Technical design:** *(Directional guidance, not implementation specification.)*

```
@bot message → extract plain text → strip whitespace
                                    ↓
                            text is empty? → "在呢，有什么可以帮你的？"
                                    ↓ no
                    KnowledgeBase.search(question)
                      ↓                    ↓
                 score >= threshold    score < threshold
                      ↓                    ↓
              return KB answer    LLM available?
                                  ↓           ↓
                                 yes          no
                                  ↓           ↓
                          LLM + disclaimer  降级回复
```

**Patterns to follow:**
- NoneBot2 `on_message(rule=to_me())` — 标准 @bot 响应模式
- thefuzz `partial_ratio` — Python 社区标准模糊文本匹配

**Test scenarios:**
- Happy path: AE1 — "@bot 群规是什么" → KB 命中 → 返回预设群规文本，无 AI 免责声明
- Happy path: AE2 — "@bot Python 的 GIL 是什么意思" → KB 未命中 → LLM 兜底 → 回复含 "AI 生成，仅供参考"
- Edge case: AE4 — "有人知道群规在哪看吗" (无 @) → bot 不响应
- Edge case: "@bot" (无后续文本) → 返回简短引导
- Edge case: "@bot 群gui是什么" (拼写变体) → fuzzy 匹配命中 "群规" 条目 (score >= 75)
- Edge case: KB 两阶段均未命中 + LLM 不可用 → 返回降级提示
- Error path: LLM API 超时 3 次 → `LLMUnavailableException` → 返回降级提示

**Verification:**
- 用 5 种不同问法提问同一 KB 条目（如 "群规" / "群里有啥规矩" / "rules" / "群规定" / "本群规则"），至少 3 种命中 KB
- KB 管理指令：`@bot kb add 问题 | 答案` → 条目追加到 knowledge_base.yml
- KB 管理指令仅允许 superusers 执行，普通用户收到 "权限不足" 提示

---

### U5. B站 BV 号解析插件

**Goal:** 自动检测群消息中的 BV 号，调用 B站 API 获取视频信息，回复图文卡片。支持后续 @bot 请求该视频的 AI 摘要。

**Requirements:** R4, R5, R6

**Dependencies:** U3 (缓存, LLM 客户端)

**Files:**
- Create: `src/plugins/bilibili/__init__.py`, `src/plugins/bilibili/matchers.py`, `src/plugins/bilibili/parser.py`, `src/plugins/bilibili/renderer.py`
- Create: `tests/test_bilibili/test_parser.py`, `tests/test_bilibili/test_matchers.py`

**Approach:**
- `parser.py`: 正则 `\b(BV[1-9A-HJ-NP-Za-km-z]{10})\b` 提取 BV 号（仅大写 BV 前缀，避免小写误报）。`fetch_video_info(bvid)` 调用 `https://api.bilibili.com/x/web-interface/view?bvid=...`，返回 `VideoInfo` dataclass。视频信息通过 `TTLCache` 缓存 1 小时
- `matchers.py`: `on_message(rule=has_bv_number, priority=90, block=False)` 处理所有含 BV 号的消息。在 handler 入口立即检查 `event.user_id == event.self_id` 防止自触发。单消息最多处理 3 个 BV 号，合并为一条回复。API 调用结果缓存命中时直接返回
- `renderer.py`: `format_video_card(VideoInfo) → Message` 输出 `MessageSegment.image(cover_url) + MessageSegment.text(title+author+stats+duration)`
- R6 会话上下文：`parser.py` 维护 `group_bv_context: dict[str, tuple[float, str]]` — 每组最近解析的 BV 号 + 5 分钟 TTL。当用户 @bot "总结一下这个视频" 时，从上下文获取 bvid 并调用 LLM 生成摘要。过期或空时引导用户发送 BV 号
- `on_command("总结", rule=to_me())` 单独处理摘要请求

**Patterns to follow:**
- NoneBot2 `on_message` with custom `Rule` — 标准关键词检测模式
- B站 API `/x/web-interface/view` 端点 — 公开接口，无需登录态

**Test scenarios:**
- Happy path: AE3 — "这个视频 BV1xx411c7mD 好搞笑" → 自动回复视频标题、UP 主、播放量、封面图
- Happy path: AE3 + R6 — BV 卡片发出后 @bot "总结一下这个视频" → LLM 生成内容摘要
- Edge case: 消息含 2 个 BV 号 → 合并为一条消息展示两个视频信息
- Edge case: 消息含 5 个 BV 号 → 仅展示前 3 个，回复 "检测到5个BV号，仅展示前3个"
- Edge case: bot 自己的 BV 卡片消息 → `self_id` 过滤，不触发二次检测
- Edge case: b23.tv 短链 → v1 不处理，静默忽略
- Edge case: 小写 "bv1xx411c7md" → 不触发检测
- Error path: B站 API 返回 404 (无效 BV 号) → 静默跳过，不发送错误消息（避免刷屏）
- Error path: B站 API 返回 429 (限流) → 跳过该 BV，不重试
- Error path: R6 摘要请求但 BV 上下文已过期 → 回复 "请发送或引用BV号，我已不记得刚才的视频了"

**Verification:**
- 解析 10 种不同格式的含 BV 号消息（URL 中、文本中、中英混合、多行等），BV 提取准确率 100%
- BV 检测到回复的端到端延迟 <5 秒（含 API 调用，不含 LLM 摘要）
- 连续发送同一 BV 号两次 → 第二次从缓存返回，无 API 调用

---

### U6. 每日群聊总结插件

**Goal:** 通过 APScheduler 在每日固定时间（默认 22:00）自动发送群聊总结：热词 TOP 5 + 发言活跃榜 + 潜水提醒。

**Requirements:** R7, R12, R13

**Dependencies:** U1 (config.yml), U2 (消息存储), U3 (LLM 客户端, 用于总结润色)

**Files:**
- Create: `src/plugins/summary/__init__.py`, `src/plugins/summary/scheduler.py`, `src/plugins/summary/generator.py`
- Create: `tests/test_summary/test_generator.py`

**Approach:**
- `scheduler.py`: 在 `@driver.on_startup` 中注册 APScheduler cron job (22:00, Asia/Shanghai)。注册前检查 config 中的 `plugins.summary.enabled`。发送前检查数据库中 `last_summary_date` 防止重启时重复发送。若 bot 错过多天（如宕机），不回溯生成
- `generator.py`: 查询当日 `00:00` 至今的所有 GroupMessage（按 group_id 过滤，排除 `self_id`）。`jieba` 分词 + 停用词过滤 → Counter 取 TOP 5 热词。`user_id` 分组计数 → TOP 3 活跃榜。对比近 7 天发言用户 vs 今日发言用户 → 潜水提醒列表
- LLM 可用时调用 LLM 润色自然语言总结；不可用时使用纯模板化的 stats-only 格式（含说明 "AI 服务不可用，仅展示统计数据"）
- 如果当日无消息 → 发送 "今天群里还没有消息哦~" 或静默跳过（由 config 控制）
- 植物在线时长不足（如 bot 崩溃半天后恢复），可在总结中酌情添加说明

**Technical design:** *(Directional guidance, not implementation specification.)*

```
22:00 cron trigger
    ↓
check enabled && same group not already sent today
    ↓
query today's messages (WHERE group_id=? AND timestamp >= today 00:00)
    ↓
messages count == 0? → (config decides: silent or "今日暂无群聊")
    ↓
compute: jieba cut → Counter → TOP 5 hot words
compute: user_id count → TOP 3 active speakers
compute: 7-day users - today users → inactive list
    ↓
LLM available? → yes: polish with LLM / no: stats-only template
    ↓
send to group → record last_summary_date in DB
```

**Patterns to follow:**
- `nonebot_plugin_apscheduler` — NoneBot2 社区标准定时任务方案
- jieba 中文分词 — Python 中文 NLP 的事实标准

**Test scenarios:**
- Happy path: AE6 — 22:00 触发，200 条当日消息 → 输出含热词 TOP 5 + 发言 TOP 3 + 潜水提醒的总结
- Edge case: 当日 0 条消息 → 按 config 决定静默跳过或发送 "今日暂无群聊"
- Edge case: 重启后同一日再次触发 → `last_summary_date` 去重，不重复发送
- Edge case: 仅含表情包/sticker 的消息 → `plain_text` 为空，不计入热词但计入发言数
- Error path: LLM 不可用 → 回退到纯统计模板，含 "AI 服务不可用" 说明
- Error path: 数据库查询超时 → 捕获异常，记录日志，不崩溃定时任务

**Verification:**
- 手动修改 cron 为每分钟触发，验证总结在下一分钟准时发送
- 修改系统时间后重启，同一天的定时任务不会重复发送
- 用 50 条模拟消息验证热词排序和发言排行的正确性

---

### U7. 群友画像插件

**Goal:** 持续采集群消息数据，按需生成群友画像报告：发言统计 + 兴趣标签 + 关系网络。支持通过 @bot 指令查询。

**Requirements:** R7, R8, R9, R10, R11

**Dependencies:** U2 (消息存储), U3 (LLM 客户端, 可选用于标签推断增强)

**Files:**
- Create: `src/plugins/profile/__init__.py`, `src/plugins/profile/collector.py`, `src/plugins/profile/analyzer.py`, `src/plugins/profile/matchers.py`, `src/plugins/profile/models.py`
- Create: `tests/test_profile/test_analyzer.py`, `tests/test_profile/test_matchers.py`

**Approach:**
- `collector.py`: `on_message(rule=is_group_msg, priority=99, block=False)` — 最低优先级非阻塞消息采集器。fire-and-forget 写入 GroupMessage 到数据库。过滤 `self_id` (R11)。过滤 `event.user_id == event.self_id`
- `analyzer.py`:
  - `compute_stats(user_id, group_id)` — 统计：总发言数、日均发言、活跃时段分布（按小时分组）
  - `infer_tags(user_id, group_id, min_occurrences=3)` — jieba 分词 + TOPIC_TAG_MAP 关键词→标签映射。规则匹配优先，LLM 可选增强（但 LLM 不可用时退回纯规则）
  - `build_relation_graph(group_id)` — 查询所有含 @mention 的消息，构建 user_id → {target: count} 的关系图
- `matchers.py`: `on_message(rule=to_me(), priority=10)` 处理画像查询。必须通过 OneBot v11 `at` segment 指定目标用户（精确 user_id 解析）。纯文本名称尝试模糊匹配；多个候选时列出 "你是想查谁？", 无人匹配时 "未找到该群友"
- `models.py`: 画像相关 dataclass — `UserStats`, `UserProfile` (组装 stats + tags + relations)
- 冷启动处理：总发言 <10 条 → 回复 "该群友发言较少，暂时无法生成画像"
- 数据保留策略：原始消息 90 天，聚合统计永久。退群成员数据保留但不可查 (R11)

**Patterns to follow:**
- fire-and-forget collector 模式 — 不影响消息处理主链路
- jieba + 关键词词典的规则匹配 — 中文兴趣标签推断的轻量方案

**Test scenarios:**
- Happy path: AE5 — "@bot 看看小明的画像" (@mention 小明) → 返回发言统计 + 兴趣标签 + 关系网络文本报告
- Edge case: 目标用户发言 <10 条 → 回复冷启动提示，不生成报告
- Edge case: 目标用户不存在于群内 → 回复 "未找到该群友"
- Edge case: 纯文本名称匹配到多个候选 → 列出候选列表 "你是想查 小明A、小明B 中的哪一位？"
- Edge case: 查询已退群成员的画像 → 回复 "该用户已不在群内"
- Error path: 数据库查询异常 → 返回通用错误提示 "画像数据暂时无法获取"

**Verification:**
- 插入 100 条已知内容的模拟消息 → 画像报告中的发言计数、热词、活跃时段与实际数据一致
- 插入含特定关键词（"原神"、"Python" 各 5 次）的消息 → 兴趣标签正确推断为 "游戏"、"编程"
- 插入含 @mention 关系的消息 → 关系图正确反映互动频率

---

## System-Wide Impact

- **Interaction graph:** U4 (Q&A) 和 U7 (Profile query) 共享 `to_me()` 消息入口 → 通过 handler priority 区分（Q&A priority=10 可能先于 Profile=10，需精确分配或合并到同一个 intent classifier）。U5 (BV) 和 U4 可通过同一消息同时触发 → BV block=False 确保不阻止 Q&A 处理
- **Error propagation:** 所有 LLM 调用经过 `llm_router.py` 统一降级层。插件级捕获 `LLMUnavailableException` 并返回功能特定的降级回复。数据库错误在 `Depends(get_db_session)` provider 中统一处理
- **State lifecycle risks:** SQLite WAL 模式下 bot 进程崩溃不会损坏数据库。`TTLCache` 的内存缓存在进程重启后自然清空（可接受）。APScheduler job 在热重载时可能残留 → 注册前检查是否已存在
- **API surface parity:** 所有插件通过 OneBot v11 `Message` 格式回复 → `renderer.py` 可被多个插件复用。LLM 调用统一经过 `llm_router` → 单一成本追踪点
- **Integration coverage:** U4+U5: @bot + BV 号同时存在时两者均正常触发。U6+U2: 定时总结读取的消息必须包含 U4/U5 运行期间写入的消息。U7+U4: 画像采集不区分消息类型，包括 Q&A 交互
- **Unchanged invariants:** 不改变 OneBot v11 协议层的消息格式。不修改 NoneBot2 框架内部的 matcher 调度逻辑。不扩展 config.yml 之外的配置来源

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| NapCatQQ 协议不稳定导致断连 | OneBot v11 反向 WebSocket 内置 30 秒自动重连；NoneBot2 侧 driver 保持常驻监听 |
| LLM API 成本超预期（群友频繁 @bot） | U3 内置每用户 rate limiter (10 次/分钟)；config 中设置 daily_budget_usd 上限并记录日志 |
| B站 API 需要 WBI 签名而直接 HTTP 无法工作 | Deferred to Implementation 中明确如果签名复杂度超预期则切换 `bilibili-api-python` 库 |
| SQLite 在高频群中日写入量超预期 | WAL 模式 + 批量写入（每 10 条消息 flush 一次）可缓解；必要时切换 PostgreSQL（SQLAlchemy 抽象层支持） |
| jieba 分词对网络用语/梗的效果差 | TOPIC_TAG_MAP 支持 owner 手动扩展关键词 → 标签映射；初始填充 30-50 个常见映射 |

---

## Documentation / Operational Notes

- **部署**: Windows 11 上推荐 NSSM 注册为 Windows 服务实现后台运行和崩溃自动重启；或直接用 `python bot.py` 开发调试
- **NapCatQQ 配置**: 需在 NapCatQQ WebUI 中配置反向 WebSocket 连接至 `ws://127.0.0.1:8080/onebot/v11/ws`
- **首次启动**: 当 bot QQ 号首次登录时，可能需要在 NapCatQQ 侧完成扫码/验证
- **知识库**: `data/knowledge_base.yml` 由 owner 手动编辑或通过 @bot kb add 指令添加
- **日志**: 位于 `logs/bot.log`，10MB 轮转，保留 7 天。JSON 格式方便 grep/jq 查询
- **每日总结暂停**: 在 config.yml 设置 `plugins.summary.enabled: false` 并重启 bot

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-05-21-qq-bot-requirements.md](../brainstorms/2026-05-21-qq-bot-requirements.md)
- External docs: NoneBot2 — https://nonebot.dev/
- External docs: OneBot v11 — https://github.com/botuniverse/onebot-11
- External docs: B站 API 合集 — https://github.com/SocialSisterYi/bilibili-API-collect
- External docs: NapCatQQ — https://github.com/NapNeko/NapCatQQ
- External docs: bilibili-api-python — https://github.com/Nemo2011/bilibili-api
