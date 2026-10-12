@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo ============================================================
echo   Сборка J.A.R.V.I.S. для Windows
echo ============================================================

where python >nul 2>nul || (echo [!] Python не найден в PATH & pause & exit /b 1)

for /f "delims=" %%v in ('python -c "import sys;sys.path.insert(0,'.');from core.version import __version__;print(__version__)"') do set VER=%%v
echo [*] Версия: %VER%
echo.

echo [1/5] Окружение сборки...
if not exist ".venv-build\" python -m venv .venv-build
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
python -m pip install --quiet SpeechRecognition pyttsx3 pygame psutil requests pyautogui pyinstaller || goto :fail
python -m pip install --quiet PyAudio || echo [!] PyAudio не встал — голосовой ввод в сборке работать не будет

echo [2/5] PyInstaller...
rmdir /s /q build\pyi 2>nul
pyinstaller build\jarvis.spec --noconfirm --clean --distpath dist --workpath build\pyi || goto :fail

echo [3/5] Портативный архив...
powershell -NoProfile -Command ^
  "Compress-Archive -Path 'dist\JARVIS\*' -DestinationPath 'dist\JARVIS-%VER%-windows-portable.zip' -Force" || goto :fail

echo [4/5] Установщик (Inno Setup)...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "!ISCC!" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "!ISCC!" (
    "!ISCC!" /DAppVersion=%VER% build\installer.iss || goto :fail
) else (
    echo [!] Inno Setup 6 не найден.
    echo     Скачайте: https://jrsoftware.org/isdl.php   ^(или: winget install JRSoftware.InnoSetup^)
    echo     Портативный zip уже собран, установщик пропущен.
)

echo [5/5] Контрольные суммы...
powershell -NoProfile -Command ^
  "Get-ChildItem dist\*.zip,dist\*.exe -ErrorAction SilentlyContinue | Get-FileHash -Algorithm SHA256 | ForEach-Object { $_.Hash.ToLower() + '  ' + (Split-Path $_.Path -Leaf) }" > dist\SHA256SUMS.txt

echo.
echo ============================================================
echo   Готово. Файлы в папке dist\
echo ============================================================
dir /b dist\*.exe dist\*.zip dist\SHA256SUMS.txt 2>nul
echo.
if "%CI%"=="" pause
exit /b 0

:fail
echo.
echo [!] Сборка прервана с ошибкой.
if "%CI%"=="" pause
exit /b 1
