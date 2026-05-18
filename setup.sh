#!/bin/bash
# AI Daily — 项目初始化脚本
# 新环境 clone 后运行一次即可

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== AI Daily Setup ==="

# 1. Python 依赖
echo "[1/3] Installing Python dependencies..."
pip3 install -q feedparser httpx openai anthropic 2>/dev/null || pip install -q feedparser httpx openai anthropic
echo "  Python deps OK"

# 2. 软链接: prototype/data → data (前端开发时需要)
echo "[2/3] Creating symlinks..."
if [ ! -L prototype/data ]; then
    ln -sf ../data prototype/data
    echo "  prototype/data → ../data OK"
else
    echo "  prototype/data already exists"
fi

# 3. 环境变量模板
echo "[3/3] Checking .env..."
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# AI Daily — 环境变量
# 填入你的 API key，取消注释

# DeepSeek API (默认 AI provider)
# export AI_DAILY_DS_KEY=sk-xxx

# Anthropic API (可选，--provider claude 时使用)
# export AI_DAILY_ANTHROPIC_KEY=sk-ant-xxx

# Server酱 WeChat Push (可选，不设则不推送微信)
# export AI_DAILY_SERVERCHAN_KEY=SCTxxx
EOF
    echo "  .env template created — please edit with your API keys"
else
    echo "  .env already exists"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Quick start:"
echo "  python3 server.py              # Local dev server"
echo "  python3 pipeline/run.py         # Run pipeline manually"
echo ""
echo "launchd schedule: edit ~/Library/LaunchAgents/com.ai-daily.pipeline.plist"
echo "  then: launchctl load ~/Library/LaunchAgents/com.ai-daily.pipeline.plist"
