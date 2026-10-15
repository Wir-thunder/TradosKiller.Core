@echo off
chcp 65001 >nul
title Instalador do TradosKiller CAT Tool

echo =====================================================================
echo           INSTALADOR TRADOSKILLER CAT TOOL - SETUP AUTOMATICO
echo =====================================================================
echo.

:: 1. Verifica presenca do Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao foi encontrado no PATH do sistema!
    echo Por favor, instale o Python 3.10+ (marcando "Add Python to PATH") em https://www.python.org/
    pause
    exit /b 1
)

echo [1/4] Python detectado com sucesso.
echo.

:: 2. Cria/Verifica o ambiente virtual
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Criando ambiente virtual Python (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao criar ambiente virtual!
        pause
        exit /b 1
    )
) else (
    echo [2/4] Ambiente virtual existente detectado.
)
echo.

:: 3. Instala dependencias
echo [3/4] Instalando/atualizando dependencias do requirements.txt...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [AVISO] Ocorreu uma advertencia durante a instalacao dos pacotes.
)
echo [OK] Dependencias instaladas com sucesso.
echo.

:: 4. Cria atalhos no Desktop e no Menu Iniciar
echo [4/4] Criando atalho na Area de Trabalho e Menu Iniciar...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
    "$shortcut = $ws.CreateShortcut(\"$desktop\TradosKiller.lnk\"); " ^
    "$shortcut.TargetPath = '%SCRIPT_DIR%.venv\Scripts\pythonw.exe'; " ^
    "$shortcut.Arguments = '\"%SCRIPT_DIR%main.py\"'; " ^
    "$shortcut.WorkingDirectory = '%SCRIPT_DIR%'; " ^
    "$icon = '%SCRIPT_DIR%assets\app_icon.ico'; " ^
    "if (Test-Path $icon) { $shortcut.IconLocation = $icon }; " ^
    "$shortcut.Description = 'TradosKiller CAT Tool'; " ^
    "$shortcut.Save(); " ^
    "$startMenu = [Environment]::GetFolderPath('Programs'); " ^
    "$shortcutSM = $ws.CreateShortcut(\"$startMenu\TradosKiller.lnk\"); " ^
    "$shortcutSM.TargetPath = '%SCRIPT_DIR%.venv\Scripts\pythonw.exe'; " ^
    "$shortcutSM.Arguments = '\"%SCRIPT_DIR%main.py\"'; " ^
    "$shortcutSM.WorkingDirectory = '%SCRIPT_DIR%'; " ^
    "if (Test-Path $icon) { $shortcutSM.IconLocation = $icon }; " ^
    "$shortcutSM.Save(); " ^
    "Write-Host '[OK] Atalho criado na Area de Trabalho e no Menu Iniciar!'"

echo.
echo =====================================================================
echo         INSTALACAO CONCLUIDA COM SUCESSO!
echo         Atalho disponivel na Area de Trabalho: "TradosKiller"
echo =====================================================================
echo.

set /p INICIAR="Deseja iniciar o TradosKiller agora? (S/N): "
if /i "%INICIAR%"=="S" (
    start "" "%SCRIPT_DIR%.venv\Scripts\pythonw.exe" "%SCRIPT_DIR%main.py"
)

exit /b 0
