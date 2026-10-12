"""
Подстановка реального адреса репозитория вместо заглушки.
Используется скриптами setup_github.sh / setup_github.bat.

Запуск:  python tools/_patch_repo.py логин/название
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def patch(repo: str) -> int:
    if "/" not in repo or repo.count("/") != 1 or not all(repo.split("/")):
        print("Нужен формат логин/название, например ivanov/jarvis")
        return 1

    url = f"https://github.com/{repo}"
    changed: list[str] = []

    # 1. README — все упоминания заглушки
    p = ROOT / "README.md"
    if p.exists():
        s = p.read_text(encoding="utf-8")
        new = s.replace("username/jarvis", repo).replace("ваш-логин/jarvis", repo)
        if new != s:
            p.write_text(new, encoding="utf-8")
            changed.append("README.md")

    # 2. Установщик Windows — ссылки «Поддержка» и «Обновления»
    p = ROOT / "build" / "installer.iss"
    if p.exists():
        s = p.read_text(encoding="utf-8")
        new = re.sub(r'(#define\s+AppURL\s+")[^"]*(")', rf"\g<1>{url}\g<2>", s)
        if new != s:
            p.write_text(new, encoding="utf-8")
            changed.append("build/installer.iss")

    # 3. Настройки по умолчанию — чтобы автообновление заработало сразу
    p = ROOT / "core" / "config.py"
    if p.exists():
        s = p.read_text(encoding="utf-8")
        new = re.sub(r'("update_repo":\s*)"[^"]*"', rf'\g<1>"{repo}"', s, count=1)
        if new != s:
            p.write_text(new, encoding="utf-8")
            changed.append("core/config.py")

    for c in changed:
        print(f"      обновлён {c}")
    if not changed:
        print("      нечего менять (адрес уже подставлен)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(patch(sys.argv[1]))
