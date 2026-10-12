"""
Проверка логики активационного слова, подтверждений и режима беседы.
Действия заглушены — ничего реально не открывается.
Запуск:  python tests/test_assistant.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import brain, commands, config  # noqa: E402

commands.open_url = lambda url: True
commands.open_path = lambda p: True
commands.launch_app = lambda k: True
commands.set_volume = lambda d, s=10: True
commands.shutdown_pc = lambda delay=20: True
commands.reboot_pc = lambda delay=20: True
commands.lock_screen = lambda: True
brain.weather = lambda city, lang: f"[погода:{city}]"
brain.wiki = lambda q, lang: f"[вики:{q}]"

from core.assistant import Assistant  # noqa: E402

cfg = dict(config.DEFAULTS)
cfg["play_boot_phrase"] = False
cfg["follow_up_window"] = 12

EVENTS = []
a = Assistant(cfg, on_event=lambda k, t, e=None: EVENTS.append((k, t)))
a.voice.muted = True  # не пытаемся издавать звук


def step(phrase, voice=True):
    EVENTS.clear()
    if voice:
        a.handle_voice(phrase)
    else:
        a.handle_text(phrase)
    return EVENTS


def last(kind=None):
    for k, t in reversed(EVENTS):
        if kind is None or k == kind:
            return t
    return None


ok = fail = 0


def check(label, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"OK   {label}")
    else:
        fail += 1
        print(f"FAIL {label}   {detail}")


print("=== активационное слово ===")
step("открой гугл")
check("без имени команда игнорируется", last("system", ) is not None and "мимо" in (last("system") or ""))

step("джарвис")
check("на имя отвечает «Да, сэр?»", "сэр" in (last("jarvis") or "").lower())

step("открой гугл")
check("после имени команда без имени работает (окно 12 с)",
      "открываю" in (last("jarvis") or "").lower(), last("jarvis"))

a.awake_until = 0
step("джарвис открой ютуб")
check("имя + команда в одной фразе", "открываю" in (last("jarvis") or "").lower(), last("jarvis"))

a.awake_until = 0
step("слушай джарвис какая погода")
check("имя в середине фразы", "[погода:" in (last("jarvis") or ""), last("jarvis"))

print("\n=== подтверждения ===")
a.awake_until = 0
step("джарвис выключи компьютер")
check("опасное действие спрашивает подтверждение", a.pending_confirm == "shutdown", a.pending_confirm)
step("да")
check("«да» подтверждает", "подтверждено" in (last("jarvis") or "").lower(), last("jarvis"))

a.awake_until = 0
step("джарвис перезагрузи компьютер")
step("нет")
check("«нет» отменяет", "отменено" in (last("jarvis") or "").lower(), last("jarvis"))
check("состояние подтверждения сброшено", a.pending_confirm is None)

print("\n=== текстовый ввод (имя не нужно) ===")
step("который час", voice=False)
check("текст без имени работает", "сейчас" in (last("jarvis") or "").lower(), last("jarvis"))
step("джарвис сколько будет 12 умножить на 12", voice=False)
check("имя в тексте вырезается", "144" in (last("jarvis") or ""), last("jarvis"))

print("\n=== английский ===")
step("jarvis what time is it")
check("распознан английский", "sir" in (last("jarvis") or "").lower(), last("jarvis"))

print("\n=== прочее ===")
a.awake_until = 0
step("джарвис абракадабра бессмыслица")
check("непонятная команда -> ответ «не распознал»",
      "не распознал" in (last("jarvis") or "").lower(), last("jarvis"))

step("джарвис стоп")
check("«стоп» прерывает речь", "прервана" in (last("system") or "").lower(), last("system"))

a.shutdown()
print("\n" + "-" * 60)
print(f"Успешно: {ok}   Провалено: {fail}")
sys.exit(0 if fail == 0 else 1)
