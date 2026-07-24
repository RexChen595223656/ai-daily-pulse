#!/bin/bash
# AI Daily — 一键部署脚本
# 同步 prototype + 数据到 gh-pages 分支，推送源码和部署

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$ROOT/deploy"

echo "=== AI Daily Deploy ==="

# 1. Sync prototype HTML to deploy
echo "[1/4] Syncing prototype → deploy..."
cp "$ROOT/prototype/index.html" "$DEPLOY_DIR/index.html"

# 2. Sync pipeline output data
echo "[2/4] Syncing data → deploy..."
mkdir -p "$DEPLOY_DIR/data/daily/trends"
cp "$ROOT/data/daily/latest.json" "$DEPLOY_DIR/data/daily/"
cp "$ROOT/data/daily/index.json" "$DEPLOY_DIR/data/daily/"
# Copy trend data
cp "$ROOT/data/daily/trends/latest.json" "$DEPLOY_DIR/data/daily/trends/" 2>/dev/null || true
# Copy historical files too
for f in "$ROOT/data/daily/20"*.json; do
  [ -f "$f" ] && cp "$f" "$DEPLOY_DIR/data/daily/"
done

# 3. Push gh-pages (deploy)
echo "[3/4] Pushing gh-pages..."
cd "$DEPLOY_DIR"
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard data/daily/)" ]; then
  git add index.html data/daily/
  git commit -m "部署: $(date '+%Y-%m-%d %H:%M')" || true
  git push origin gh-pages --force
  echo "  gh-pages ✓"
else
  echo "  gh-pages (no changes)"
fi

# 4. Push source (main)
echo "[4/4] Pushing source..."
cd "$ROOT"
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard pipeline/ prototype/ worker/ docs/ data/ *.py *.sh)" ]; then
  git add pipeline/ prototype/ worker/ docs/ data/ server.py deploy.sh .gitignore CLAUDE.md
  git commit -m "更新: $(date '+%Y-%m-%d %H:%M')" || true
  git push origin main
  echo "  main ✓"
else
  echo "  main (no changes)"
fi

echo "=== Done ==="
echo "https://rexchen595223656.github.io/ai-daily-pulse/"
