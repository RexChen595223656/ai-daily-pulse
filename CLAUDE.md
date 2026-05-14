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
│   ├── run.py                    # 主脚本: Fetch → Filter → Dedup → AI Process → Output
│   └── run.sh                    # launchd 调用的 shell wrapper
├── server.py                     # 本地开发服务器（静态文件 + /api/refresh + /api/status）
├── data/daily/                   # 流水线输出 (latest.json + YYYY-MM-DD.json + index.json)
├── prototype/                    # 可交互原型（本地开发用）
│   ├── index.html                # 单文件日报页面（赛博朋克风）
│   └── data/                     # 数据副本（非软链接，需手动同步）
├── deploy/                       # GitHub Pages 部署目录（独立 git 仓库）
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
pipeline/run.py (4 阶段)
    ├── 1. Fetch: httpx 并行抓取，15s 超时
    ├── 2. Filter: 时间窗口(24h) → AI关键词 → 标题去重(0.6)
    ├── 3. AI Process: DeepSeek/Claude 分类+摘要+毒舌+要点+冷笑话
    └── 4. Output: JSON 写入 → 微信推送(Server酱)
    ↓
data/daily/latest.json  ← 前端 prototype/index.html 加载
```

**前端数据源：**
- 日报资讯：`data/daily/latest.json`（流水线产出）
- 趋势看板：`artificialanalysis.ai` API v2（LLM/图片/视频），1000次/天
- 历史：`data/daily/index.json` → 按日期加载 `YYYY-MM-DD.json`

**AI Provider 切换：** 默认 DeepSeek，`--provider claude` 切换。API key 优先级：CLI 参数 > 环境变量 > config.py

## 常用命令

```bash
# 本地开发服务器（带 token 保护的刷新）
python3 server.py
# → http://localhost:8080/prototype/index.html
# 手动刷新: GET /api/refresh?token=zhimai-refresh-2026
# 状态查询: GET /api/status

# 完整流水线（手动）
python3 pipeline/run.py

# 仅抓取+过滤（不调用 AI API）
python3 pipeline/run.py --fetch-only

# 指定 AI provider
python3 pipeline/run.py --provider claude
```

## 定时调度

launchd plist: `~/Library/LaunchAgents/com.ai-daily.pipeline.plist`
- 每天 8:00 触发 `pipeline/run.sh`
- 日志：`data/daily/launchd.log`

## 部署

`deploy/` 是独立 git 仓库，push 到 `git@github.com:RexChen595223656/ai-daily-pulse.git`，GitHub Pages 自动部署。

部署前需手动同步：
```bash
cp prototype/index.html deploy/index.html
cp -r data/daily/* deploy/data/daily/
cd deploy && git add -A && git commit -m "更新日报数据" && git push
```

## 已知限制

1. **前端 API key 可见** — `deploy/index.html` 含 artificialanalysis.ai key（`aa_xxx`）。静态托管无法隐藏前端 key，该 API 有每日 1000 次限制，portfolio 场景可接受。如需保护，可加一层后端代理。
2. **deploy/ 需手动同步** — prototype 改完后需手动 cp 到 deploy/ 并 push，未做自动化。

## 遵循方法论

../personal-knowledge-base/AI产品经理工作方法论.md
