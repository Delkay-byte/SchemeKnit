@echo off
setlocal enabledelayedexpansion

echo ======================================
echo   SchemeKnit Desktop 1.0.5 Build
echo ======================================
echo.

:: Check prerequisites
echo [1/6] Checking prerequisites...
where node >nul 2>&1
if %errorlevel% neq 0 ( echo ERROR: Node.js missing & exit /b 1 )
where npm >nul 2>&1
if %errorlevel% neq 0 ( echo ERROR: npm missing & exit /b 1 )
echo    [OK] Node.js, npm found
echo.

:: Install Electron dependencies
echo [2/6] Installing Electron dependencies...
cd /d "%~dp0"
call npm install
if %errorlevel% neq 0 ( echo ERROR: electron deps failed & exit /b 1 )
echo    [OK] Electron dependencies installed
echo.

:: Build Next.js static export for desktop
echo [3/6] Building Next.js frontend (static export)...
cd /d "%~dp0\..\frontend"
call npm run build:desktop
if %errorlevel% neq 0 ( echo ERROR: frontend build failed & exit /b 1 )
echo    [OK] Frontend exported to out/ directory
echo.

:: Build Python backend with PyInstaller (uses desktop\build-venv)
echo [4/6] Building Python backend with PyInstaller...
cd /d "%~dp0"
call build-venv\Scripts\python.exe -m PyInstaller backend.spec --clean --noconfirm
if %errorlevel% neq 0 ( echo ERROR: backend build failed & exit /b 1 )
echo    [OK] Backend built to dist\schemeknit-backend\
echo.

:: Verify build inputs exist
echo [5/6] Verifying build inputs...
if not exist "dist\schemeknit-backend\schemeknit-backend.exe" ( echo ERROR: backend exe missing & exit /b 1 )
if not exist "..\frontend\out\index.html" ( echo ERROR: frontend export missing & exit /b 1 )
echo    [OK] backend + frontend artifacts present
echo.

:: Build Electron installer
echo [6/6] Building Electron installer...
cd /d "%~dp0"
call npx electron-builder --win
if %errorlevel% neq 0 ( echo ERROR: installer build failed & exit /b 1 )
echo    [OK] Installer built
echo.

echo ======================================
echo   Build Complete!
echo ======================================
echo.
echo Installer: release\SchemeKnit-Setup-1.0.5-x64.exe
echo.
