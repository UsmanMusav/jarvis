#!/usr/bin/env python3
"""
J.A.R.V.I.S. — голосовой помощник для компьютера.

Запуск:
    python main.py              — обычный запуск с интерфейсом
    python main.py --console    — режим без окна (команды с клавиатуры в терминале)
    python main.py --check      — проверить, что установлено и что работает
    python main.py --say "..."  — произнести фразу голосом Джарвиса (проверка звука)
    python main.py --update     — проверить и поставить обновление из GitHub
    python main.py --version    — показать версию
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def check():
    from core import config, speech
    from core.audio_out import Voice

    print("=" * 58)
    print("  J.A.R.V.I.S. — проверка системы")
    print("=" * 58)
    print(f"Python           : {sys.version.split()[0]}")
    import platform

    print(f"Система          : {platform.system()} {platform.release()}")

    try:
        import tkinter  # noqa

        print("tkinter (окно)   : да")
    except Exception as e:
        print(f"tkinter (окно)   : НЕТ — {e}")

    cfg = config.ensure_exists()
    v = Voice(cfg)
    st = v.status()
    print(f"Проигрыватель    : {st['player']}")
    print(f"Локальный синтез : {st['local_tts']}")
    print(f"edge-tts         : {st['edge_tts']}")
    print(f"Клипы Джарвиса   : русских {st['clips_ru']}, английских {st['clips_en']}")

    for k, val in speech.diagnostics().items():
        print(f"{k:17}: {val}")

    mics = speech.list_microphones()
    if mics:
        print("\nМикрофоны:")
        for i, n in enumerate(mics):
            print(f"  [{i}] {n}")
    else:
        print("\nМикрофоны не найдены (нужен пакет PyAudio).")

    for mod in ("psutil", "requests", "pyautogui", "pygame", "pyttsx3",
                "speech_recognition", "vosk", "edge_tts"):
        try:
            __import__(mod)
            print(f"  + {mod}")
        except Exception:
            print(f"  - {mod}  (не установлен)")

    print("\nКонфиг: " + str(config.CONFIG_PATH))
    v.stop()


def console():
    from core import config
    from core.assistant import Assistant

    cfg = config.ensure_exists()

    def ev(kind, text, extra=None):
        prefix = {"user": "ВЫ    >", "jarvis": "JARVIS>", "error": "ОШИБКА>",
                  "display": "", "system": "       "}.get(kind, "")
        print(f"{prefix} {text}")

    a = Assistant(cfg, on_event=ev)
    a.boot()
    print("\nРежим терминала. Введите команду (или «микрофон» для голоса, «выход» для выхода).\n")
    try:
        while True:
            try:
                line = input("❯ ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line.lower() in ("выход", "exit", "quit", "q"):
                break
            if line.lower() in ("микрофон", "mic"):
                if a.toggle_listening():
                    print("Микрофон включён. Скажите: «Джарвис, открой гугл».")
                else:
                    print("Микрофон выключен или недоступен.")
                continue
            a.handle_text(line)
    finally:
        a.shutdown()


def say(text: str):
    from core import config
    from core.audio_out import Voice

    cfg = config.ensure_exists()
    v = Voice(cfg)
    lang = "en" if sum(1 for c in text if "a" <= c.lower() <= "z") > \
        sum(1 for c in text if "а" <= c.lower() <= "я") else "ru"
    v.say(text, lang=lang, wait=True)
    v.stop()


def update_cli():
    """Проверка и установка обновления из командной строки."""
    from core import config
    from core.updater import Updater
    from core.version import __version__

    cfg = config.ensure_exists()
    up = Updater(cfg, on_event=lambda k, t: print(f"[{k}] {t}"))
    print(f"Текущая версия: {__version__}")
    print(f"Тип установки : {up.describe()}")
    repo = up.repo()
    if not repo:
        print("\nРепозиторий не задан. Откройте config.json и впишите, например:")
        print('    "update_repo": "username/jarvis"')
        print(f"Файл: {config.CONFIG_PATH}")
        return 1
    print(f"Репозиторий   : {repo}\nПроверяю…")
    rel = up.check(force=True)
    if rel is None:
        return 0
    print(f"\nНайдена версия {rel.version} от {rel.published}")
    if rel.notes:
        print("-" * 50)
        print(rel.notes[:800])
        print("-" * 50)
    asset = rel.pick_asset()
    if not asset:
        print("Для вашей системы файла в релизе нет.")
        return 1
    print(f"Файл: {asset['name']}  ({asset['size'] / 1048576:.1f} МБ)")
    if input("Установить? [y/N] ").strip().lower() not in ("y", "yes", "д", "да"):
        print("Отменено.")
        return 0

    last = [-1]

    def progress(frac):
        pct = int(frac * 100)
        if pct != last[0] and pct % 5 == 0:
            last[0] = pct
            print(f"\r  загрузка: {pct:3d} %", end="", flush=True)

    path = up.download(rel, progress)
    print()
    if not path:
        return 1
    return 0 if up.apply(path) else 1


def main():
    args = sys.argv[1:]
    if args and args[0] in ("--version", "-v"):
        from core.version import __version__

        print(__version__)
        return 0
    if args and args[0] in ("--update", "-u"):
        return update_cli()
    if args and args[0] in ("--check", "-c", "check"):
        return check()
    if args and args[0] in ("--console", "--cli"):
        return console()
    if args and args[0] == "--say":
        return say(" ".join(args[1:]) or "Проверка связи, сэр.")

    try:
        from core.ui import run
    except Exception as e:
        print(f"Не удалось запустить графический интерфейс: {e}")
        print("Запускаю режим терминала…\n")
        return console()
    run()


if __name__ == "__main__":
    main()
