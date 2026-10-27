@echo off
setlocal
cd /d "%~dp0"
title Alpha Investigation System

echo ==================================================
echo   Alpha Investigation System - starting...
echo ==================================================

where docker >nul 2>&1
if errorlevel 1 goto :no_docker
docker info >nul 2>&1
if errorlevel 1 goto :docker_not_running

if exist ".env" goto :env_ready
copy ".env.example" ".env" >nul
echo [i] Created .env from .env.example
:env_ready

findstr /r /c:"^LLM_API_KEY=..*" /c:"^LLM_1_KEY=..*" ".env" >nul
if errorlevel 1 (
    echo.
    echo [!] No model key in .env ^(LLM_API_KEY or LLM_1_KEY^) - the app will start, but case analysis will fail.
    echo     Open .env, set LLM_API_KEY, then run this file again.
    echo.
)

rem A shared secret so only the app can call the analysis workflow.
findstr /r /c:"^ALPHA_WEBHOOK_TOKEN=..*" ".env" >nul
if errorlevel 1 (
    for /f %%t in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')"') do (
        (echo.& echo ALPHA_WEBHOOK_TOKEN=%%t)>>".env"
    )
    echo [i] Added ALPHA_WEBHOOK_TOKEN to .env
)

set "WEB_PORT=8601"
for /f "usebackq tokens=1,* delims==" %%a in (".env") do if /i "%%a"=="WEB_PORT" set "WEB_PORT=%%b"

echo [1/2] Building and starting services (first run can take a few minutes)...
docker compose up -d --build --wait --remove-orphans
if errorlevel 1 goto :compose_failed

echo [2/2] Opening http://localhost:%WEB_PORT%
start "" "http://localhost:%WEB_PORT%"

echo ==================================================
echo   Alpha web is running: http://localhost:%WEB_PORT%
echo   To stop it:        docker compose down
echo ==================================================
pause
exit /b 0

:no_docker
echo [x] Docker is not installed. Install Docker Desktop: https://www.docker.com/products/docker-desktop/
pause
exit /b 1

:docker_not_running
echo [x] Docker is installed but not running. Start Docker Desktop, wait until it is ready, then try again.
pause
exit /b 1

:compose_failed
echo.
echo [x] Some services failed to start. Last log lines:
docker compose logs --tail 40
pause
exit /b 1
