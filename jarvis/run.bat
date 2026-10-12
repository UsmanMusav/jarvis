@echo off
chcp 65001 >nul
title J.A.R.V.I.S.
cd /d "%~dp0"

echo ============================================
echo   J.A.R.V.I.S. - запуск
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python не найден. Установите Python 3.10+ с python.org
    echo     ВАЖНО: при установке отметьте "Add Python to PATH"
    pause
    exit /b 1
)

if not exist ".venv\" (
    echo [*] Создаю виртуальное окружение...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

if not exist ".venv\.installed" (
    echo [*] Устанавливаю зависимости, это займёт пару минут...
    python -m pip install --upgrade pip --quiet
    python -m pip install SpeechRecognition pyttsx3 pygame psutil requests pyautogui --quiet
    echo [*] Ставлю PyAudio (микрофон)...
    python -m pip install PyAudio --quiet || python -m pip install pipwin --quiet && pipwin install pyaudio
    echo ok> .venv\.installed
)

python main.py %*
pause
