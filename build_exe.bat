@echo off
echo ========================================
echo Building SerrebiTorrent All-In-One EXE
echo ========================================

:: Kill running instances to avoid file-in-use errors
taskkill /F /IM SerrebiTorrent.exe /T >nul 2>&1

:: Ensure dependencies
:: pip install -r requirements.txt

:: Clean previous artifacts
if exist build rd /s /q build
if exist dist rd /s /q dist

:: Run PyInstaller
pyinstaller SerrebiTorrent.spec --noconfirm

echo.
echo ========================================
echo SUCCESS! Your portable EXE is in 'dist'.
echo No other files are needed to run.
echo ========================================