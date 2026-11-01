@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%~dp0"

if exist "%ROOT%ps2coop.exe" (
    start "" "%ROOT%ps2coop.exe" %* --game "%ROOT%"
    exit /b 0
)

set "PYEXE="
set "PYARGS="

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYEXE=py"
        set "PYARGS=-3"
    )
)

if not defined PYEXE (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYEXE=python"
    )
)

if not defined PYEXE if exist "%ROOT%runtime\python\python.exe" set "PYEXE=%ROOT%runtime\python\python.exe"

if not defined PYEXE (
    echo Python 3.10+ nao encontrado. Baixando uma copia portatil...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%tools\bootstrap-python.ps1"
    if errorlevel 1 (
        echo.
        echo Nao foi possivel preparar o Python portatil.
        echo Instale o Python 3.10 ou maior em https://www.python.org/downloads/windows/
        echo e execute este arquivo de novo.
        pause
        exit /b 1
    )
    set "PYEXE=%ROOT%runtime\python\python.exe"
)

if not exist "%ROOT%app.py" (
    echo app.py nao encontrado na pasta do PS2 Co-op.
    pause
    exit /b 1
)

echo Iniciando PS2 Co-op...
"%PYEXE%" %PYARGS% "%ROOT%app.py" %* --game "%ROOT%"
if errorlevel 1 (
    echo.
    echo O PS2 Co-op terminou com erro. Veja a mensagem acima.
    pause
)
endlocal
