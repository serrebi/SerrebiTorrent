@echo off
setlocal enableextensions enabledelayedexpansion

cd /d "%~dp0"

if "%~4"=="" (
    echo Usage: update_helper.bat ^<install_dir^> ^<new_dir^> ^<backup_dir^> ^<exe_name^>
    exit /b 2
)

set "INSTALL_DIR=%~1"
set "NEW_DIR=%~2"
set "BACKUP_DIR=%~3"
set "EXE_NAME=%~4"

if not exist "%INSTALL_DIR%" (
    echo Install directory not found: "%INSTALL_DIR%"
    exit /b 2
)

if not exist "%NEW_DIR%" (
    echo Staging directory not found: "%NEW_DIR%"
    exit /b 2
)

echo Waiting for %EXE_NAME% to exit...
:wait_loop
tasklist /FI "IMAGENAME eq %EXE_NAME%" | find /I "%EXE_NAME%" >nul
if %errorlevel%==0 (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

echo Swapping application folders...
if exist "%BACKUP_DIR%" (
    rmdir /s /q "%BACKUP_DIR%"
)

move "%INSTALL_DIR%" "%BACKUP_DIR%"
if %errorlevel% neq 0 (
    echo Failed to move current install to backup.
    exit /b 1
)

move "%NEW_DIR%" "%INSTALL_DIR%"
if %errorlevel% neq 0 (
    echo Failed to move new version into place. Rolling back...
    if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"
    if exist "%BACKUP_DIR%" move "%BACKUP_DIR%" "%INSTALL_DIR%"
    exit /b 1
)

echo Update applied. Restarting...
start "" "%INSTALL_DIR%\%EXE_NAME%"
exit /b 0
