#!/usr/bin/env bash
# Сборка J.A.R.V.I.S. для Linux: архив .tar.gz + install.sh + ярлык в меню
set -e
cd "$(dirname "$0")/.."

echo "============================================================"
echo "  Сборка J.A.R.V.I.S. для Linux"
echo "============================================================"

VER=$(python3 -c "import sys;sys.path.insert(0,'.');from core.version import __version__;print(__version__)")
echo "[*] Версия: $VER"

echo "[1/4] Окружение сборки…"
[ -d .venv-build ] || python3 -m venv .venv-build
# shellcheck disable=SC1091
source .venv-build/bin/activate
pip install --upgrade pip -q
pip install -q SpeechRecognition pyttsx3 pygame psutil requests pyautogui pyinstaller
pip install -q PyAudio || echo "[!] PyAudio не встал: sudo apt install portaudio19-dev"

echo "[2/4] PyInstaller…"
rm -rf build/pyi dist/JARVIS
pyinstaller build/jarvis.spec --noconfirm --clean --distpath dist --workpath build/pyi

echo "[3/4] Ярлык и установщик…"
cat > dist/JARVIS/jarvis.desktop <<DESKTOP
[Desktop Entry]
Type=Application
Name=J.A.R.V.I.S.
GenericName=Голосовой помощник
Comment=Голосовое управление компьютером
Exec=__EXEC__
Icon=__ICON__
Terminal=false
Categories=Utility;AudioVideo;
Keywords=voice;assistant;jarvis;голос;помощник;
StartupNotify=true
DESKTOP

cat > dist/JARVIS/install.sh <<'INSTALL'
#!/usr/bin/env bash
# Установка J.A.R.V.I.S. в домашнюю папку (без root)
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/jarvis"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"

echo "Установка в $DEST …"
mkdir -p "$DEST" "$BIN" "$APPS"
cp -R "$SRC/." "$DEST/"
chmod +x "$DEST/JARVIS"

ln -sf "$DEST/JARVIS" "$BIN/jarvis"

for s in 16 32 48 64 128 256 512; do
  if [ -f "$DEST/_internal/assets/icons/icon_$s.png" ]; then
    mkdir -p "$ICONS/${s}x${s}/apps"
    cp "$DEST/_internal/assets/icons/icon_$s.png" "$ICONS/${s}x${s}/apps/jarvis.png"
  fi
done

sed -e "s|__EXEC__|$DEST/JARVIS|" -e "s|__ICON__|jarvis|" \
    "$DEST/jarvis.desktop" > "$APPS/jarvis.desktop"
chmod +x "$APPS/jarvis.desktop"

command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
command -v gtk-update-icon-cache  >/dev/null && gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true

echo
echo "Готово. Запуск: команда  jarvis  или значок в меню приложений."
echo "Если нет звука/микрофона:  sudo apt install portaudio19-dev espeak-ng"
echo "Удаление:  rm -rf \"$DEST\" \"$BIN/jarvis\" \"$APPS/jarvis.desktop\""
INSTALL
chmod +x dist/JARVIS/install.sh

echo "[4/4] Архив и контрольные суммы…"
TAR="JARVIS-$VER-linux-x86_64.tar.gz"
( cd dist && tar czf "$TAR" JARVIS && sha256sum ./*.tar.gz | sed 's|\./||' > SHA256SUMS.txt )

echo
echo "Готово:"
ls -lh "dist/$TAR" dist/SHA256SUMS.txt
echo
echo "Установка у пользователя:  tar xzf $TAR && ./JARVIS/install.sh"
