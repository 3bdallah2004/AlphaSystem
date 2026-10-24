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

findstr /r /c:"^LLM_API_KEY=..*" ".env" >nul
if errorlevel 1 (
    echo.
    echo [!] LLM_API_KEY is empty in .env - the app will start, but case analysis will fail.
    echo     Open .env, set LLM_API_KEY, then run this file again.
    echo.
)

set "APP_PORT=8501"
for /f "usebackq tokens=1,* delims==" %%a in (".env") do if /i "%%a"=="APP_PORT" set "APP_PORT=%%b"

echo [1/2] Building and starting services (first run can take a few minutes)...
docker compose up -d --build --wait
if errorlevel 1 goto :compose_failed

echo [2/2] Opening http://localhost:%APP_PORT%
start "" "http://localhost:%APP_PORT%"

echo ==================================================
echo   Alpha is running:  http://localhost:%APP_PORT%
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
