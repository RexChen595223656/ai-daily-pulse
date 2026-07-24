# AI Daily — 智脉（AI 行业日报）

## 项目简介

"5 分钟看懂 AI 圈"的日报产品。15 源聚合 AI 行业动态 + AI 摘要 + 原文链接 + 大模型趋势看板 + 微信推送。

**定位：** AI PM 学习项目，阶段二（可演示产出）。对外可展示为 portfolio piece。

**线上地址：** https://rexchen595223656.github.io/ai-daily-pulse/

## 项目结构

```
ai-daily/
├── pipeline/                     # 自动化日报流水线
│   ├── config.py                 # 15 个信息源 + AI 关键词 + 流水线参数
│   ├── run.py                    # 主脚本: Fetch → Filter → Dedup → AI Process → Output → Auto Deploy
│   └── run.sh                    # launchd 调用的 shell wrapper
├── worker/                       # Cloudflare Worker（AA API 代理，隐藏前端 key）
│   ├── worker.js                 # 代理逻辑
│   └── wrangler.toml             # Worker 配置
├── server.py                     # 本地开发服务器（静态文件 + /api/refresh + /api/status）
├── deploy.sh                     # 一键部署脚本（同步原型+数据到 gh-pages 分支）
├── data/daily/                   # 流水线输出 (latest.json + YYYY-MM-DD.json + index.json)
├── prototype/                    # 可交互原型（本地开发用）
│   ├── index.html                # 单文件日报页面（赛博朋克风）
│   └── data -> ../data           # 软链接到流水线输出
├── deploy/                       # GitHub Pages 部署目录（跟踪 gh-pages 分支）
│   ├── index.html                # 与 prototype/index.html 同步
│   └── data/daily/               # 部署用静态数据
├── docs/requirements/            # PM 文档
│   ├── 2026-05-13-F-01-AI-Daily需求分析.md
│   ├── 2026-05-13-F-06-AI-Daily功能拆解.md
│   └── 2026-05-13-F-07-AI-Daily交互原型说明.md
└── CLAUDE.md                     # 本文件
```

## 架构与数据流

```
RSS 源 (15个)
    ↓
pipeline/run.py (5 阶段 + 自动部署)
    ├── 1. Fetch: httpx 并行抓取，15s 超时
    ├── 2. Filter: 时间窗口(24h) → AI关键词 → 标题去重(0.6)
    ├── 3. AI Process: DeepSeek/Claude 分类+摘要+毒舌+要点+冷笑话
    ├── 4. Output: JSON 写入 → 微信推送(Server酱)
    ├── 5. Trends: AA API → Cloudflare Worker 代理 → 趋势数据持久化
    └── 6. Auto Deploy: deploy.sh → GitHub Pages 自动更新
    ↓
data/daily/latest.json  ← 前端 prototype/index.html 加载
    ↓
deploy.sh → gh-pages 分支 → GitHub Pages
```

**前端数据源：**
- 日报资讯：`data/daily/latest.json`（流水线产出）
- 趋势看板：`data/daily/trends/latest.json`（流水线产出，每日更新）→ 降级到 AA API 实时拉取 → 降级到内联快照
- 历史：`data/daily/index.json` → 按日期加载 `YYYY-MM-DD.json`

**AI Provider 切换：** 默认 DeepSeek，`--provider claude` 切换。API key 优先级：CLI 参数 > 环境变量 > config.py

## 常用命令

```bash
# 本地开发服务器（带 token 保护的刷新）
python3 server.py
# → http://localhost:8080/prototype/index.html
# 手动刷新: GET /api/refresh?token=<TOKEN>
#   Token 通过环境变量 AI_DAILY_REFRESH_TOKEN 设置
# 状态查询: GET /api/status

# 完整流水线（手动，含自动部署）
python3 pipeline/run.py

# 仅抓取+过滤（不调用 AI API）
python3 pipeline/run.py --fetch-only

# 指定 AI provider
python3 pipeline/run.py --provider claude

# 一键部署（手动触发）
bash deploy.sh

# 新环境初始化
bash setup.sh

# 单元测试
python3 -m pytest tests/ -v
```

## 定时调度

launchd plist: `~/Library/LaunchAgents/com.ai-daily.pipeline.plist`
- 每天 8:00 触发 `pipeline/run.sh`
- 日志：`data/daily/launchd.log`
- 流水线末尾自动调用 `deploy.sh`，网站和微信同步更新
- 环境变量（API keys）通过 plist 注入，不写入代码

## 部署

仓库：`git@github.com:RexChen595223656/ai-daily-pulse.git`

| 分支 | 内容 |
|------|------|
| `main` | 完整源码（pipeline/worker/server/docs/prototype） |
| `gh-pages` | 部署文件（index.html + data/），GitHub Pages 自动部署 |

**全自动：** 流水线跑完自动执行 `deploy.sh`，无需手动操作。

**手动部署：** `bash deploy.sh`（同步 prototype + data → push 两个分支）

## Cloudflare Worker

Worker 代理 AA API，前端不直接持有 API key。

| 项目 | 值 |
|------|-----|
| URL | `https://ai-daily-trends.rexchen.workers.dev` |
| Secret | `AA_API_KEY`（通过 `wrangler secret put` 设置） |
| 管理 | `cd worker && npx wrangler deploy` |

## 已知限制

1. **workers.dev 国内访问可能慢** — 趋势看板 API 走 Cloudflare Worker 代理，国内网络偶有超时，前端会降级到内联快照数据，不影响页面展示。
2. **每日首次访问加载偏慢** — GitHub Pages + 前端直连 AA API（经 Worker），首屏依赖 3 个 API 请求。

## 遵循方法论

../personal-knowledge-base/AI产品经理工作方法论.md
