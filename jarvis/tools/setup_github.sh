#!/usr/bin/env bash
# ============================================================
#  Привязка проекта к вашему репозиторию на GitHub.
#
#  Что делает:
#    1. подставляет ваш адрес вместо заглушки username/jarvis
#       в README.md, build/installer.iss и core/config.py;
#    2. делает git init, первый коммит и push;
#    3. по желанию ставит тег v<версия> — это запускает сборку
#       установщиков и публикацию релиза на GitHub Actions.
#
#  Запуск:
#      chmod +x tools/setup_github.sh
#      tools/setup_github.sh ваш-логин/jarvis
# ============================================================
set -e
cd "$(dirname "$0")/.."

REPO="$1"
if [ -z "$REPO" ] || [ "${REPO#*/}" = "$REPO" ]; then
  echo "Укажите репозиторий в формате логин/название, например:"
  echo "    tools/setup_github.sh ivanov/jarvis"
  exit 1
fi

VERSION=$(python3 -c "import sys;sys.path.insert(0,'.');from core.version import __version__;print(__version__)")
URL="https://github.com/$REPO"

echo "============================================================"
echo "  Репозиторий : $URL"
echo "  Версия      : $VERSION"
echo "============================================================"
echo
echo "Перед запуском создайте ПУСТОЙ репозиторий здесь:"
echo "    https://github.com/new     (без README, без .gitignore)"
echo
read -r -p "Репозиторий создан? Продолжаем? [y/N] " a
case "$a" in y|Y|д|Д|да|yes) ;; *) echo "Отменено."; exit 0 ;; esac

echo
echo "[1/4] Подставляю адрес в файлы проекта…"
python3 - "$REPO" <<'PY'
import re, sys
from pathlib import Path

repo = sys.argv[1]
url = f"https://github.com/{repo}"
changed = []

# README: все упоминания заглушки
p = Path("README.md"); s = p.read_text(encoding="utf-8")
new = s.replace("username/jarvis", repo).replace("ваш-логин/jarvis", repo)
if new != s:
    p.write_text(new, encoding="utf-8"); changed.append(str(p))

# Установщик Windows: ссылки «Поддержка» и «Обновления»
p = Path("build/installer.iss"); s = p.read_text(encoding="utf-8")
new = re.sub(r'(#define\s+AppURL\s+")[^"]*(")', rf'\g<1>{url}\g<2>', s)
if new != s:
    p.write_text(new, encoding="utf-8"); changed.append(str(p))

# Настройки по умолчанию: чтобы автообновление работало сразу после установки
p = Path("core/config.py"); s = p.read_text(encoding="utf-8")
new = re.sub(r'("update_repo":\s*)"[^"]*"', rf'\g<1>"{repo}"', s, count=1)
if new != s:
    p.write_text(new, encoding="utf-8"); changed.append(str(p))

for c in changed:
    print(f"      обновлён {c}")
if not changed:
    print("      нечего менять (адрес уже подставлен)")
PY

echo
echo "[2/4] Проверяю, что всё работает…"
python3 tests/test_commands.py  > /dev/null && echo "      команды      OK"
python3 tests/test_assistant.py > /dev/null && echo "      диалог       OK"
python3 tests/test_updater.py   > /dev/null && echo "      обновление   OK"

echo
echo "[3/4] Git…"
if [ ! -d .git ]; then
  git init -q
  echo "      репозиторий создан"
fi
git add -A
if git diff --cached --quiet; then
  echo "      нечего коммитить"
else
  git commit -q -m "J.A.R.V.I.S. $VERSION — голосовой помощник с установщиком и автообновлением"
  echo "      коммит сделан"
fi
git branch -M main
git remote remove origin 2>/dev/null || true
git remote add origin "$URL.git"
echo "      origin -> $URL.git"
git push -u origin main

echo
echo "[4/4] Релиз"
read -r -p "Поставить тег v$VERSION и запустить сборку установщиков? [y/N] " b
case "$b" in
  y|Y|д|Д|да|yes)
    git tag "v$VERSION" -f
    git push origin "v$VERSION" -f
    echo
    echo "Сборка пошла. Следить тут:"
    echo "    $URL/actions"
    echo "Через 10–15 минут установщики появятся тут:"
    echo "    $URL/releases/latest"
    ;;
  *)
    echo "Пропущено. Когда захотите выпустить релиз:"
    echo "    git tag v$VERSION && git push origin v$VERSION"
    ;;
esac

echo
echo "============================================================"
echo "  Готово.  $URL"
echo "============================================================"
