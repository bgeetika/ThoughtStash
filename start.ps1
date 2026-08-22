# ThoughtStash — Windows PowerShell Launcher

Write-Host "🧠 Starting ThoughtStash on Windows..." -ForegroundColor Cyan

# 1. Check Python
$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
} else {
    Write-Host "❌ Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.10+ from python.org and check 'Add Python to PATH'."
    exit 1
}

# 2. Virtual Environment
if (-not (Test-Path ".venv")) {
    Write-Host "📦 Creating virtual environment (.venv)..." -ForegroundColor Yellow
    & $pythonCmd -m venv .venv
}

# Activate venv
$activateScript = ".venv\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    & $activateScript
}

# 3. Dependencies
Write-Host "📦 Installing / verifying dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt -q

# 4. Check GEMINI_API_KEY
if (-not $env:GEMINI_API_KEY) {
    if (Test-Path ".env") {
        # python-dotenv will load it inside app
        Write-Host "🔑 Found .env file." -ForegroundColor Green
    } else {
        Write-Host "⚠️ Warning: GEMINI_API_KEY is not set." -ForegroundColor Yellow
        Write-Host "   Set it via: `$env:GEMINI_API_KEY = 'your-key' or create a .env file."
    }
}

# 5. Launch
$port = if ($env:PORT) { $env:PORT } else { "8877" }
$hostIp = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }

Write-Host ""
Write-Host "🧠 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "   ThoughtStash — Voice Thought Capture" -ForegroundColor White
Write-Host "   Running at: http://$hostIp`:$port" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

python -m uvicorn app:app --host $hostIp --port $port --reload
