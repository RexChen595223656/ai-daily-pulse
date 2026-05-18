#!/bin/bash
# AI Daily Pipeline — launchd wrapper
# Logs output to data/daily/pipeline.log

cd "/Users/chenbaijian/my-claude/ai-daily" || exit 1
mkdir -p data/daily

# Load API keys: prefer env vars (CI), fall back to macOS Keychain (local launchd)
if [ -z "$AI_DAILY_DS_KEY" ]; then
    export AI_DAILY_DS_KEY=$(security find-generic-password -a chenbaijian -s ai-daily-ds-key -w 2>/dev/null)
fi
if [ -z "$AI_DAILY_ANTHROPIC_KEY" ]; then
    export AI_DAILY_ANTHROPIC_KEY=$(security find-generic-password -a chenbaijian -s ai-daily-anthropic-key -w 2>/dev/null)
fi
if [ -z "$AI_DAILY_SERVERCHAN_KEY" ]; then
    export AI_DAILY_SERVERCHAN_KEY=$(security find-generic-password -a chenbaijian -s ai-daily-serverchan-key -w 2>/dev/null)
fi

if [ -z "$AI_DAILY_DS_KEY" ]; then
    echo "[ERROR] No API key found. Set AI_DAILY_DS_KEY env var or store in Keychain."
    exit 1
fi

exec 1> >(tee -a data/daily/pipeline.log)
exec 2>&1

echo "=== AI Daily Pipeline $(date '+%Y-%m-%d %H:%M:%S') ==="
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 pipeline/run.py
echo "=== Done $(date '+%Y-%m-%d %H:%M:%S') ==="
