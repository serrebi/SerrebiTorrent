@echo off
echo ========================================
echo Building SerrebiTorrent Executive...
echo ========================================

:: Ensure dependencies are up to date
pip install -r requirements.txt

:: Clean previous builds
if exist build rd /s /q build
if exist dist rd /s /q dist

:: Run PyInstaller
pyinstaller SerrebiTorrent.spec --noconfirm

echo.
echo ========================================
echo Build complete! Check the 'dist' folder.
echo ========================================
pause
