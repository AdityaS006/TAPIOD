@echo off
echo ===================================================
echo   Starting TAPIOD Backend (LiteLLM Proxy)
echo ===================================================
start "TAPIOD Backend" cmd /k "cd gateway && set PYTHONIOENCODING=utf-8 && .\venv\Scripts\activate && litellm --config litellm_config.yaml --port 4000"

echo ===================================================
echo   Starting TAPIOD Frontend (Next.js Dashboard)
echo ===================================================
start "TAPIOD Frontend" cmd /k "cd tapiod-web && npm run dev"

echo Boot sequence initiated! Two terminal windows should now pop up.
echo Close this window at any time.
