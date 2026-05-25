@echo off
setlocal

cd /d %~dp0

set "PYTHON_CMD="
python --version >nul 2>&1
if %errorlevel%==0 (
  set "PYTHON_CMD=python"
) else (
  py -3 --version >nul 2>&1
  if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
  )
)

if "%PYTHON_CMD%"=="" (
  echo [ERROR] Python 3 が見つかりません。Pythonをインストールしてください。
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] .venv を作成しています...
  call %PYTHON_CMD% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] .venv の作成に失敗しました。
    pause
    exit /b 1
  )
)

call .venv\Scripts\activate
if errorlevel 1 (
  echo [ERROR] 仮想環境の有効化に失敗しました。
  pause
  exit /b 1
)

echo [INFO] 依存パッケージをインストールしています...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] requirements.txt のインストールに失敗しました。
  pause
  exit /b 1
)

start "" powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8080/control'"

echo [INFO] FastAPI を起動します: http://127.0.0.1:8080
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080

endlocal
