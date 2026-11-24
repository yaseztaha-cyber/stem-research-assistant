@echo off
echo Building STEM Research Assistant Desktop App...
echo.

if not exist "python-embed\python.exe" (
    echo [0/4] python-embed missing - run setup_python_embed.bat first!
    exit /b 1
)

echo [1/4] Building frontend...
cd ..\frontend
call npm run build
if errorlevel 1 (
    echo Frontend build failed!
    exit /b 1
)

echo.
echo [2/4] Building desktop app (PyInstaller onedir)...
cd ..\desktop
call pyinstaller --clean --noconfirm app.spec
if errorlevel 1 (
    echo PyInstaller build failed!
    exit /b 1
)

echo.
echo [3/4] Packaging distribution zip...
cd dist
if exist "STEM-Research-Assistant-win64.zip" del "STEM-Research-Assistant-win64.zip"
tar -a -c -f "STEM-Research-Assistant-win64.zip" "STEM Research Assistant"
if errorlevel 1 (
    echo Zip packaging failed!
    exit /b 1
)
cd ..

echo.
echo [4/4] Done!
echo.
echo App folder: dist\STEM Research Assistant\
echo   (double-click "STEM Research Assistant.exe")
echo.
echo Distribute:  dist\STEM-Research-Assistant-win64.zip
echo.
pause
