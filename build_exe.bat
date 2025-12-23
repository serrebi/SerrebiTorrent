@echo off
echo ========================================
echo Building SerrebiTorrent Distribution
echo ========================================

:: Kill running instances to avoid file-in-use errors
taskkill /F /IM SerrebiTorrent.exe /T >nul 2>&1

:: Clean previous artifacts
if exist build rd /s /q build
if exist dist rd /s /q dist

:: Run PyInstaller
pyinstaller SerrebiTorrent.spec --noconfirm

echo.
echo ========================================
echo SUCCESS! Your portable distribution is in 'dist\SerrebiTorrent'.
echo To share, ZIP the entire 'SerrebiTorrent' folder.
echo ========================================