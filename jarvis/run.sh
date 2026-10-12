#!/usr/bin/env bash
# Запуск J.A.R.V.I.S. на macOS / Linux
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  J.A.R.V.I.S. — запуск"
echo "============================================"

PY=python3
command -v $PY >/dev/null 2>&1 || { echo "[!] Python 3 не найден"; exit 1; }

if [ ! -d ".venv" ]; then
  echo "[*] Создаю виртуальное окружение…"
  $PY -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f ".venv/.installed" ]; then
  echo "[*] Устанавливаю зависимости…"
  pip install --upgrade pip -q
  pip install SpeechRecognition pyttsx3 pygame psutil requests pyautogui -q
  echo "[*] Ставлю PyAudio (микрофон)…"
  if ! pip install PyAudio -q; then
    echo "[!] PyAudio не собрался."
    echo "    Linux:  sudo apt install -y portaudio19-dev python3-pyaudio espeak-ng"
    echo "    macOS:  brew install portaudio"
    echo "    Затем:  pip install PyAudio"
  fi
  touch .venv/.installed
fi

exec python main.py "$@"
