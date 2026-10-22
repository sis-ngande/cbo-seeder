@echo off
rem CBO Seeder
rem   run                  open the web page
rem   run --port 8600      open the web page on another port
rem   run --help           terminal options
rem   run [options]        run from the terminal, e.g. run --only ema
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo The .venv folder is missing. Set it up first, see README.md.
    exit /b 1
)

if "%~1"=="" (
    .venv\Scripts\python.exe -m streamlit run ui.py
) else if "%~1"=="--port" (
    .venv\Scripts\python.exe -m streamlit run ui.py --server.port %2
) else (
    .venv\Scripts\python.exe app.py %*
)
