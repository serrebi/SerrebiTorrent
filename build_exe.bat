@echo off
setlocal enableextensions enabledelayedexpansion

set "APP_NAME=SerrebiTorrent"
set "EXE_NAME=SerrebiTorrent.exe"
set "VERSION_FILE=app_version.py"
set "MANIFEST_NAME=SerrebiTorrent-update.json"
set "DEFAULT_SIGNTOOL=C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"
set "GITHUB_OWNER=serrebi"
set "GITHUB_REPO=SerrebiTorrent"

if "%SIGNTOOL_PATH%"=="" (
    set "SIGNTOOL_PATH=%DEFAULT_SIGNTOOL%"
)

set "MODE=%~1"
if "%MODE%"=="" set "MODE=build"

if /I "%MODE%"=="help" goto :usage
if /I not "%MODE%"=="release" if /I not "%MODE%"=="build" if /I not "%MODE%"=="dry-run" goto :usage

set "DRY_RUN=0"
if /I "%MODE%"=="dry-run" set "DRY_RUN=1"

echo ========================================
echo SerrebiTorrent build: %MODE%
echo ========================================

set "ROOT=%~dp0"
pushd "%ROOT%"

if /I "%MODE%"=="release" (
    where git >nul 2>&1 || (echo Git not found in PATH.& goto :error)
    where gh >nul 2>&1 || (echo GitHub CLI ^(gh^) not found in PATH.& goto :error)
    call :detect_github
    echo Fetching tags...
    git fetch --tags
    if errorlevel 1 (
        echo Failed to fetch tags.
        goto :error
    )
)

if /I "%MODE%"=="release" (
    call :compute_version_and_notes || goto :error
    echo Next version: !NEXT_VERSION!
    if %DRY_RUN%==1 (
        echo DRY RUN: would update %VERSION_FILE% to !NEXT_VERSION!.
    ) else (
        call :update_version_file || goto :error
    )
) else if /I "%MODE%"=="dry-run" (
    set "RELEASE_NOTES=%TEMP%\SerrebiTorrent_release_notes.txt"
    call :compute_version_and_notes || goto :error
    echo Next version: !NEXT_VERSION!
) else (
    call :read_current_version || goto :error
    set "NEXT_VERSION=!CURRENT_VERSION!"
)

if %DRY_RUN%==1 (
    echo DRY RUN: would build, sign, and zip version !NEXT_VERSION!.
    if /I "%MODE%"=="release" (
        echo DRY RUN: would create manifest, commit, tag, push, and create GitHub release.
    )
    popd
    exit /b 0
)

echo Cleaning previous build artifacts...
taskkill /F /IM %EXE_NAME% /T >nul 2>&1
if exist build rd /s /q build
if exist dist rd /s /q dist
if exist build (
    powershell -NoProfile -Command "Remove-Item -Recurse -Force 'build'" >nul 2>&1
)
if exist dist (
    powershell -NoProfile -Command "Remove-Item -Recurse -Force 'dist'" >nul 2>&1
)
if exist build (
    echo Failed to delete build directory.
    goto :error
)
if exist dist (
    echo Failed to delete dist directory.
    goto :error
)

echo Running PyInstaller...
pyinstaller SerrebiTorrent.spec --noconfirm
if errorlevel 1 goto :error

if not exist "%SIGNTOOL_PATH%" (
    echo SignTool not found: "%SIGNTOOL_PATH%"
    goto :error
)

pushd "dist\%APP_NAME%"
echo Signing %EXE_NAME%...
"%SIGNTOOL_PATH%" sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a ".\%EXE_NAME%"
if errorlevel 1 (popd & goto :error)
popd
set "SIGNING_THUMBPRINT="
if defined SIGN_CERT_THUMBPRINT (
    set "SIGNING_THUMBPRINT=%SIGN_CERT_THUMBPRINT%"
) else (
    set "SIGNING_THUMBPRINT_FILE=%TEMP%\\SerrebiTorrent_thumbprint.txt"
    python -c "import re, subprocess, pathlib; exe=r'%CD%\\dist\\%APP_NAME%\\%EXE_NAME%'; tool=r'%SIGNTOOL_PATH%'; result=subprocess.run([tool,'verify','/pa','/v',exe], capture_output=True, text=True); data=(result.stdout or '') + (result.stderr or ''); m=re.search(r'SHA1 hash:\s*([0-9A-Fa-f]{40})', data); pathlib.Path(r'!SIGNING_THUMBPRINT_FILE!').write_text(m.group(1) if m else '')"
    if exist "!SIGNING_THUMBPRINT_FILE!" set /p SIGNING_THUMBPRINT=<"!SIGNING_THUMBPRINT_FILE!"
    if exist "!SIGNING_THUMBPRINT_FILE!" del /f /q "!SIGNING_THUMBPRINT_FILE!" >nul 2>&1
)
if defined SIGNING_THUMBPRINT set "SIGNING_THUMBPRINT=!SIGNING_THUMBPRINT: =!"

set "ZIP_NAME=%APP_NAME%-v%NEXT_VERSION%.zip"
set "ZIP_PATH=%CD%\dist\%ZIP_NAME%"
echo Creating release ZIP: %ZIP_NAME%
powershell -NoProfile -Command "Compress-Archive -Path 'dist\%APP_NAME%' -DestinationPath '%ZIP_PATH%' -Force"
if errorlevel 1 goto :error

echo Creating latest ZIP: %APP_NAME%.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\%APP_NAME%' -DestinationPath 'dist\%APP_NAME%.zip' -Force"

if /I "%MODE%"=="release" (
    call :create_manifest || goto :error
    call :git_commit_tag_push || goto :error
    call :gh_release || goto :error
)

echo ========================================
echo SUCCESS! Output is in dist\%APP_NAME%.
echo ========================================
popd
exit /b 0

:read_current_version
set "CURRENT_VERSION="
for /f "tokens=2 delims==" %%A in ('findstr /b /c:"APP_VERSION" "%VERSION_FILE%"') do set "CURRENT_VERSION=%%A"
set "CURRENT_VERSION=!CURRENT_VERSION:"=!"
set "CURRENT_VERSION=!CURRENT_VERSION: =!"
if "%CURRENT_VERSION%"=="" (
    echo Failed to read APP_VERSION from %VERSION_FILE%.
    exit /b 1
)
exit /b 0

:update_version_file
powershell -NoProfile -Command "(Get-Content '%VERSION_FILE%') -replace '^APP_VERSION\\s*=.*','APP_VERSION = \"%NEXT_VERSION%\"' | Set-Content '%VERSION_FILE%' -Encoding ASCII"
if errorlevel 1 (
    echo Failed to update %VERSION_FILE%.
    exit /b 1
)
exit /b 0

:compute_version_and_notes
if "%RELEASE_NOTES%"=="" set "RELEASE_NOTES=%CD%\release_notes.txt"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -File "tools\release_tools.ps1" -NotesPath "%RELEASE_NOTES%"`) do set "%%A"
if "%NEXT_VERSION%"=="" (
    echo Failed to compute next version.
    exit /b 1
)
exit /b 0

:create_manifest
set "MANIFEST_PATH=%CD%\dist\%MANIFEST_NAME%"
set "DOWNLOAD_URL=https://github.com/%GITHUB_OWNER%/%GITHUB_REPO%/releases/download/v%NEXT_VERSION%/%ZIP_NAME%"
python -c "import datetime, hashlib, json, pathlib; zip_path=r'%ZIP_PATH%'; h=hashlib.sha256(); f=open(zip_path,'rb'); [h.update(chunk) for chunk in iter(lambda: f.read(1024*1024), b'')]; f.close(); notes=pathlib.Path(r'%RELEASE_NOTES%').read_text(encoding='utf-8', errors='ignore'); manifest={'version':'%NEXT_VERSION%','asset_filename':'%ZIP_NAME%','download_url':'%DOWNLOAD_URL%','sha256':h.hexdigest(),'published_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'notes_summary':notes}; thumb=r'%SIGNING_THUMBPRINT%'; if thumb: manifest['signing_thumbprint']=thumb; pathlib.Path(r'%MANIFEST_PATH%').write_text(json.dumps(manifest, indent=2), encoding='utf-8')"
if errorlevel 1 (
    echo Failed to create update manifest.
    exit /b 1
)
exit /b 0

:git_commit_tag_push
git add "%VERSION_FILE%"
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "chore(release): v%NEXT_VERSION%"
    if errorlevel 1 (
        echo Git commit failed.
        exit /b 1
    )
) else (
    echo No version change to commit.
)
git tag "v%NEXT_VERSION%"
if errorlevel 1 (
    echo Git tag failed.
    exit /b 1
)
for /f "usebackq delims=" %%B in (`git rev-parse --abbrev-ref HEAD`) do set "CURRENT_BRANCH=%%B"
if "%CURRENT_BRANCH%"=="" set "CURRENT_BRANCH=main"
git push origin "%CURRENT_BRANCH%"
if errorlevel 1 (
    echo Git push failed.
    exit /b 1
)
git push origin "v%NEXT_VERSION%"
if errorlevel 1 (
    echo Git tag push failed.
    exit /b 1
)
exit /b 0

:gh_release
echo Creating GitHub release v%NEXT_VERSION%...
gh release create "v%NEXT_VERSION%" "%ZIP_PATH%" "%MANIFEST_PATH%" ^
    --title "V%NEXT_VERSION%" ^
    --notes-file "%RELEASE_NOTES%"
if errorlevel 1 (
    echo GitHub release creation failed.
    exit /b 1
)
exit /b 0

:detect_github
for /f "usebackq delims=" %%A in (`powershell -NoProfile -File "tools\get_github.ps1"`) do set "%%A"
exit /b 0

:usage
echo Usage:
echo   build_exe.bat build     ^(build + sign + zip^)
echo   build_exe.bat release   ^(full release pipeline^)
echo   build_exe.bat dry-run   ^(show actions, no changes^)
exit /b 1

:error
echo ERROR: Build failed.
popd
exit /b 1
