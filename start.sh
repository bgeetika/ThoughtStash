#!/usr/bin/env bash
set -e

# ── 1. Detect Python Binary ─────────────────────────────────────────

if command -v python3 &> /dev/null && [[ "$(python3 --version 2>&1)" != *"not found"* ]]; then
    PYTHON_BIN="python3"
elif command -v python &> /dev/null && [[ "$(python --version 2>&1)" != *"not found"* ]]; then
    PYTHON_BIN="python"
elif command -v py &> /dev/null; then
    PYTHON_BIN="py"
else
    echo "❌ Error: Python is not installed or not in PATH."
    exit 1
fi

echo "🧠 Using Python: $($PYTHON_BIN --version) ($PYTHON_BIN)"

# ── 2. Setup Virtual Environment ────────────────────────────────────

if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    $PYTHON_BIN -m venv .venv
fi

# Detect Windows/Git-Bash vs Unix activation path
if [ -f ".venv/Scripts/activate" ]; then
    # Windows / Git Bash
    source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
    # Linux / macOS / WSL
    source .venv/bin/activate
else
    echo "⚠️ Warning: Activation script not found. Proceeding with environment..."
fi

# ── 3. Install Dependencies ─────────────────────────────────────────

echo "📦 Verifying dependencies..."
pip install -q -r requirements.txt

# ── 4. Configuration & Launch ───────────────────────────────────────

PORT="${PORT:-8877}"
HOST="${HOST:-0.0.0.0}"

echo ""
echo "🧠 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   ThoughtStash — Voice Thought Capture"
echo "   Local:   http://localhost:${PORT}"
if [ "$HOST" = "0.0.0.0" ]; then
    echo "   Network: http://$(hostname).c.googlers.com:${PORT} 2>/dev/null || true"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

exec uvicorn app:app --host "$HOST" --port "$PORT" --reload
