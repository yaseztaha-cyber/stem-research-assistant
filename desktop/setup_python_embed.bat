@echo off
echo Setting up bundled embeddable Python for the desktop app...
echo.

set TARGET=%~dp0python-embed
set PYVER=3.14.0

if exist "%TARGET%" (
    echo python-embed already exists at %TARGET%
    echo Delete it first if you want a fresh setup.
    exit /b 0
)

echo [1/4] Downloading Python %PYVER% embeddable package...
powershell -Command "Invoke-WebRequest 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-embed-amd64.zip' -OutFile '%TEMP%\python-embed.zip'"
if errorlevel 1 (
    echo Download failed!
    exit /b 1
)

echo [2/4] Extracting...
powershell -Command "Expand-Archive '%TEMP%\python-embed.zip' -DestinationPath '%TARGET%' -Force"

echo [3/4] Enabling site-packages...
(
    echo python314.zip
    echo .
    echo Lib/site-packages
    echo.
    echo import site
) > "%TARGET%\python314._pth"

echo [4/4] Installing backend dependencies (fastapi, uvicorn, numpy, ...)...
powershell -Command "Invoke-WebRequest 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%TEMP%\get-pip.py'"
"%TARGET%\python.exe" "%TEMP%\get-pip.py" --no-warn-script-location
"%TARGET%\python.exe" -m pip install --no-warn-script-location -r "..\backend\requirements-desktop.txt"
if errorlevel 1 (
    echo pip install failed!
    exit /b 1
)

echo.
echo Stripping __pycache__ and test folders to reduce size...
powershell -Command "Get-ChildItem '%TARGET%\Lib\site-packages' -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; Get-ChildItem '%TARGET%\Lib\site-packages' -Directory | ForEach-Object { Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -in @('tests','testing','benchmarks') } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue }"

echo.
echo Done. python-embed ready at %TARGET%
echo Next: run build.bat
pause
