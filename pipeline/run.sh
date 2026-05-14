#!/bin/bash
# AI Daily Pipeline — launchd wrapper
# Logs output to data/daily/pipeline.log

cd "/Users/chenbaijian/my-claude/ai-daily" || exit 1
mkdir -p data/daily

exec 1> >(tee -a data/daily/pipeline.log)
exec 2>&1

echo "=== AI Daily Pipeline $(date '+%Y-%m-%d %H:%M:%S') ==="
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 pipeline/run.py
echo "=== Done $(date '+%Y-%m-%d %H:%M:%S') ==="
