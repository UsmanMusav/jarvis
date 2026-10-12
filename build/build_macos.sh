#!/usr/bin/env bash
# Сборка J.A.R.V.I.S. для macOS: JARVIS.app + установочный .dmg
set -e
cd "$(dirname "$0")/.."

echo "============================================================"
echo "  Сборка J.A.R.V.I.S. для macOS"
echo "============================================================"

VER=$(python3 -c "import sys;sys.path.insert(0,'.');from core.version import __version__;print(__version__)")
echo "[*] Версия: $VER"

echo "[1/5] Окружение сборки…"
[ -d .venv-build ] || python3 -m venv .venv-build
# shellcheck disable=SC1091
source .venv-build/bin/activate
pip install --upgrade pip -q
pip install -q SpeechRecognition pyttsx3 pygame psutil requests pyautogui pyinstaller
command -v brew >/dev/null && brew list portaudio >/dev/null 2>&1 || echo "[!] Нет portaudio: brew install portaudio"
pip install -q PyAudio || echo "[!] PyAudio не встал — голосовой ввод в сборке не заработает"

echo "[2/5] Иконка .icns…"
if command -v iconutil >/dev/null; then
  rm -rf build/jarvis.iconset && mkdir -p build/jarvis.iconset
  for s in 16 32 128 256 512; do
    cp "assets/icons/icon_${s}.png"  "build/jarvis.iconset/icon_${s}x${s}.png"
    d=$((s*2)); [ -f "assets/icons/icon_${d}.png" ] && \
      cp "assets/icons/icon_${d}.png" "build/jarvis.iconset/icon_${s}x${s}@2x.png"
  done
  iconutil -c icns build/jarvis.iconset -o assets/icons/jarvis.icns
fi

echo "[3/5] PyInstaller…"
rm -rf build/pyi dist/JARVIS.app
pyinstaller build/jarvis.spec --noconfirm --clean --distpath dist --workpath build/pyi

echo "[4/5] DMG…"
APP="dist/JARVIS.app"
[ -d "$APP" ] || APP="dist/JARVIS"
DMG="dist/JARVIS-$VER-macos.dmg"
rm -f "$DMG"
STAGE=$(mktemp -d)
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "JARVIS $VER" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

echo "[5/5] Контрольные суммы…"
( cd dist && shasum -a 256 ./*.dmg 2>/dev/null | sed 's|\./||' > SHA256SUMS.txt )

echo
echo "Готово:"
ls -lh dist/*.dmg dist/SHA256SUMS.txt
echo
echo "ВАЖНО: сборка не подписана Apple. При первом запуске"
echo "Finder -> правый клик по JARVIS.app -> «Открыть» -> «Открыть»."
echo "И дайте доступ к микрофону в Системных настройках."
