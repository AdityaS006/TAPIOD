@echo off
setlocal EnableDelayedExpansion
set "ROOT=%~dp0"

:: ── Banner ──────────────────────────────────────────────────────────────────
echo.
echo   ████████╗ █████╗ ██████╗ ██╗ ██████╗ ██████╗
echo      ██╔══╝██╔══██╗██╔══██╗██║██╔═══██╗██╔══██╗
echo      ██║   ███████║██████╔╝██║██║   ██║██║  ██║
echo      ██║   ██╔══██║██╔═══╝ ██║██║   ██║██║  ██║
echo      ██║   ██║  ██║██║     ██║╚██████╔╝██████╔╝
echo      ╚═╝   ╚═╝  ╚═╝╚═╝     ╚═╝ ╚═════╝ ╚═════╝
echo.
echo   Enterprise LLM Gateway — Setup
echo   ────────────────────────────────────────────────
echo.

:: ── .env check ──────────────────────────────────────────────────────────────
if not exist "%ROOT%gateway\.env" (
    echo   [!] gateway\.env not found — copying from .env.example
    copy "%ROOT%gateway\.env.example" "%ROOT%gateway\.env" > nul
    echo.
    echo   Open gateway\.env and add your GROQ_API_KEY before continuing.
    echo   Get a free key at https://console.groq.com
    echo.
    pause
)

:: ── FERNET_SECRET ────────────────────────────────────────────────────────────
findstr /b "FERNET_SECRET=" "%ROOT%gateway\.env" > nul 2>&1
if errorlevel 1 (
    for /f %%k in ('python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2^>nul') do (
        echo FERNET_SECRET=%%k >> "%ROOT%gateway\.env"
        echo   [OK] FERNET_SECRET generated and added to gateway\.env
    )
) else (
    echo   [OK] FERNET_SECRET already set
)

:: ── Step 1: Docker ──────────────────────────────────────────────────────────
echo   [1/5] Starting infrastructure  ^(Qdrant · PostgreSQL · Redis^)
docker compose -f "%ROOT%docker-compose.yml" up -d
if errorlevel 1 (
    echo   [ERROR] Docker failed. Is Docker Desktop running?
    pause & exit /b 1
)
echo   [OK] Infrastructure started

:: ── Step 2: Python environment ──────────────────────────────────────────────
echo.
echo   [2/5] Setting up Python environment
if not exist "%ROOT%gateway\venv" (
    python -m venv "%ROOT%gateway\venv"
    echo   [OK] Virtualenv created
)
call "%ROOT%gateway\venv\Scripts\activate.bat"
pip install -r "%ROOT%gateway\requirements.txt" -q --disable-pip-version-check
echo   [OK] Dependencies installed

:: ── Step 3: Seed Qdrant ─────────────────────────────────────────────────────
echo.
echo   [3/5] Seeding routing brain  ^(5,000 training examples^)
cd /d "%ROOT%gateway"
for /f %%i in ('curl -s http://localhost:6333/collections/routing_examples 2^>nul ^| python -c "import sys,json; d=json.load(sys.stdin); print(d[\"result\"][\"points_count\"])" 2^>nul') do set POINTS=%%i
if "!POINTS!"=="5000" (
    echo   [OK] Already seeded — skipping
) else (
    echo   [!] First run: downloads embedding model ^(~130 MB^) — takes ~3 min
    python seed_all.py
    echo   [OK] Qdrant seeded
)

:: ── Step 4: Node dependencies ───────────────────────────────────────────────
echo.
echo   [4/5] Installing dashboard dependencies
cd /d "%ROOT%tapiod-web"
if not exist "node_modules" (
    call npm install -q
)
echo   [OK] Node packages ready

:: ── Step 5: Launch all services ─────────────────────────────────────────────
echo.
echo   [5/5] Launching services in new windows
cd /d "%ROOT%"
start "TAPIOD — LiteLLM Proxy :4000" cmd /k "cd /d "%ROOT%gateway" && call venv\Scripts\activate && litellm --config litellm_config.yaml --port 4000"
timeout /t 3 /nobreak > nul
start "TAPIOD — FastAPI Gateway :4001" cmd /k "cd /d "%ROOT%gateway" && call venv\Scripts\activate && uvicorn hooks:app --port 4001 --reload"
start "TAPIOD — Dashboard :3000" cmd /k "cd /d "%ROOT%tapiod-web" && npm run dev"

:: ── Done ────────────────────────────────────────────────────────────────────
echo.
echo   ────────────────────────────────────────────────
echo   TAPIOD is starting up!
echo.
echo   Dashboard   -^>  http://localhost:3000
echo   Playground  -^>  http://localhost:3000/playground
echo   API         -^>  http://localhost:4001/api/agent/chat/completions
echo.
echo   Three terminal windows have opened — one per service.
echo   Wait a few seconds for them to fully initialize, then open the link above.
echo.
timeout /t 5 /nobreak > nul
start http://localhost:3000
