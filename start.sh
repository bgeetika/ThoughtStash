#!/bin/bash
# MindTrail — One-command launcher
set -e

cd "$(dirname "$0")"

# Check for virtual env
if [ ! -d ".venv" ]; then
    echo "🔧 Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "📦 Installing dependencies..."
pip install -q -r requirements.txt

PORT=${PORT:-8877}

echo ""
echo "🧠 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   ThoughtStash — Voice Thought Capture"
echo "   Local:  http://localhost:${PORT}"
echo "   Remote: http://$(hostname).c.googlers.com:${PORT}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

uvicorn app:app --host 0.0.0.0 --port ${PORT} --reload
