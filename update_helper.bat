@echo off
setlocal enableextensions enabledelayedexpansion

cd /d "%~dp0"

set "LOGFILE=%TEMP%\SerrebiTorrent_Update.log"
echo [INFO] Starting update script at %DATE% %TIME% > "%LOGFILE%"
echo [INFO] Arguments: %* >> "%LOGFILE%"

if "%~4"=="" (
    echo [ERROR] Missing arguments. Usage: update_helper.bat ^<install_dir^> ^<new_dir^> ^<backup_dir^> ^<exe_name^> >> "%LOGFILE%"
    exit /b 2
)

set "INSTALL_DIR=%~1"
set "NEW_DIR=%~2"
set "BACKUP_DIR=%~3"
set "EXE_NAME=%~4"

if not exist "%INSTALL_DIR%" (
    echo [ERROR] Install directory not found: "%INSTALL_DIR%" >> "%LOGFILE%"
    exit /b 2
)

if not exist "%NEW_DIR%" (
    echo [ERROR] Staging directory not found: "%NEW_DIR%" >> "%LOGFILE%"
    exit /b 2
)

echo [INFO] Waiting for %EXE_NAME% to exit... >> "%LOGFILE%"
:wait_loop
tasklist /FI "IMAGENAME eq %EXE_NAME%" | find /I "%EXE_NAME%" >nul
if %errorlevel%==0 (
    echo [INFO] %EXE_NAME% is still running, attempting to kill... >> "%LOGFILE%"
    taskkill /F /IM "%EXE_NAME%" /T >> "%LOGFILE%" 2>&1
    timeout /t 2 /nobreak >nul
    goto wait_loop
)
echo [INFO] Process %EXE_NAME% is closed. >> "%LOGFILE%"

rem Retry loop for moving INSTALL to BACKUP
set "RETRIES=0"
:backup_loop
echo [INFO] Attempting to move Install to Backup (Try %RETRIES%)... >> "%LOGFILE%"
if exist "%BACKUP_DIR%" (
    rmdir /s /q "%BACKUP_DIR%" 2>> "%LOGFILE%"
)

move "%INSTALL_DIR%" "%BACKUP_DIR%" >> "%LOGFILE%" 2>&1
if %errorlevel% equ 0 goto backup_success

set /a RETRIES+=1
if %RETRIES% lss 10 (
    echo [WARN] Move failed. Retrying in 1s... >> "%LOGFILE%"
    timeout /t 1 /nobreak >nul
    goto backup_loop
)

echo [ERROR] Failed to move current install to backup after multiple retries. >> "%LOGFILE%"
echo [ERROR] Check %LOGFILE% for details.
exit /b 1

:backup_success
echo [INFO] Backup successful. >> "%LOGFILE%"

rem Retry loop for moving NEW to INSTALL
set "RETRIES=0"
:install_loop
echo [INFO] Moving New version to Install directory (Try %RETRIES%)... >> "%LOGFILE%"
move "%NEW_DIR%" "%INSTALL_DIR%" >> "%LOGFILE%" 2>&1
if %errorlevel% equ 0 goto install_success

set /a RETRIES+=1
if %RETRIES% lss 10 (
    echo [WARN] Move failed. Retrying in 1s... >> "%LOGFILE%"
    timeout /t 1 /nobreak >nul
    goto install_loop
)

echo [ERROR] Failed to move new version into place. Rolling back... >> "%LOGFILE%"
if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%" >> "%LOGFILE%" 2>&1
if exist "%BACKUP_DIR%" move "%BACKUP_DIR%" "%INSTALL_DIR%" >> "%LOGFILE%" 2>&1
echo [ERROR] Rollback attempted. Update failed. >> "%LOGFILE%"
exit /b 1

:install_success
echo [INFO] Update applied successfully. Restarting... >> "%LOGFILE%"
start "" "%INSTALL_DIR%\%EXE_NAME%"
exit /b 0
