"""
Проверка распознавания команд БЕЗ реального выполнения действий.
Запуск:  python tests/test_commands.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import brain, commands, config  # noqa: E402
from core.assistant import detect_lang  # noqa: E402

# ------------------------------------------------- заглушки
OPENED = []
ACTIONS = []

commands.open_url = lambda url: (OPENED.append(url), True)[1]
commands.open_path = lambda p: (OPENED.append(f"path:{p}"), True)[1]
commands.launch_app = lambda k: (ACTIONS.append(f"app:{k}"), True)[1]
commands.set_volume = lambda d, s=10: (ACTIONS.append(f"vol:{d}"), True)[1]
commands.media_key = lambda k: (ACTIONS.append(f"media:{k}"), True)[1]
commands.lock_screen = lambda: (ACTIONS.append("lock"), True)[1]
commands.sleep_pc = lambda: (ACTIONS.append("sleep"), True)[1]
commands.minimize_all = lambda: (ACTIONS.append("minimize"), True)[1]
commands.close_window = lambda: (ACTIONS.append("close"), True)[1]
commands.type_text = lambda t: (ACTIONS.append(f"type:{t}"), True)[1]
commands.screenshot = lambda: (ACTIONS.append("shot"), Path("/tmp/shot.png"))[1]
brain.weather = lambda city, lang: f"[погода:{city}]"
brain.wiki = lambda q, lang: f"[вики:{q}]"

cfg = dict(config.DEFAULTS)
timers = brain.Timers()

CASES = [
    # ---------- открыть ----------
    ("открой гугл",                       "url", "google.com"),
    ("Джарвис открой ютуб",               "url", "youtube.com"),
    ("запусти вконтакте",                 "url", "vk.com"),
    ("включи почту",                      "url", "mail.google"),
    ("открой блокнот",                    "act", "app:блокнот"),
    ("открой калькулятор",                "act", "app:калькулятор"),
    ("запусти терминал",                  "act", "app:терминал"),
    ("открой папку загрузки",             "url", "path:"),
    ("открой рабочий стол",               "url", "path:"),
    ("open youtube",                      "url", "youtube.com"),
    ("открой github.com",                 "url", "github"),
    # ---------- поиск ----------
    ("найди в гугле рецепт плова",        "url", "search?q=%D1%80"),
    ("загугли погода в астрахани",        "url", "google.com/search"),
    ("включи на ютубе ac dc",             "url", "youtube.com/results"),
    ("найди котиков",                     "url", "google.com/search"),
    ("search google for python tutorial", "url", "google.com/search"),
    # ---------- управление ----------
    ("громкость больше",                  "act", "vol:up"),
    ("сделай тише",                       "act", "vol:down"),
    ("выключи звук",                      "act", "vol:mute"),
    ("громче",                            "act", "vol:up"),
    ("сделай скриншот",                   "act", "shot"),
    ("сверни все окна",                   "act", "minimize"),
    ("заблокируй компьютер",              "act", "lock"),
    ("поставь на паузу",                  "act", "media:playpause"),
    ("следующий трек",                    "act", "media:next"),
    ("volume up",                         "act", "vol:up"),
    # ---------- подтверждение ----------
    ("выключи компьютер",                 "confirm", "shutdown"),
    ("перезагрузи компьютер",             "confirm", "reboot"),
    # ---------- вопросы ----------
    ("который час",                       "say", "Сейчас"),
    ("какое сегодня число",               "say", "Сегодня"),
    ("какая погода",                      "say", "[погода:"),
    ("погода в москве",                   "say", "[погода:москве"),
    ("сколько будет 15 умножить на 7",    "say", "105"),
    ("посчитай 2+2",                      "say", "4"),
    ("сколько будет сто двадцать разделить на четыре", "say", "30"),
    ("что такое квазар",                  "say", "[вики:квазар"),
    ("состояние системы",                 "say", "систем"),
    ("привет",                            "say", ""),
    ("спасибо",                           "say", ""),
    ("расскажи анекдот",                  "say", ""),
    ("подбрось монетку",                  "say", ""),
    ("что ты умеешь",                     "say", ""),
    ("поставь таймер на 10 минут",        "say", "10"),
    ("what time is it",                   "say", "It is"),
    ("what is 8 times 9",                 "say", "72"),
]


def run_one(phrase):
    lang = detect_lang(phrase, cfg)
    # убираем имя
    t = commands.norm(phrase)
    for w in cfg["wake_words"]:
        t = t.replace(w, " ").strip()
    t = " ".join(t.split())
    rep = commands.handle(t, lang, cfg)
    if rep is None:
        rep = brain.handle(t, lang, cfg, timers)
    return rep


def main():
    ok = fail = 0
    print(f"{'ФРАЗА':<48} {'РЕЗУЛЬТАТ'}")
    print("-" * 110)
    for phrase, kind, expect in CASES:
        OPENED.clear()
        ACTIONS.clear()
        rep = run_one(phrase)
        got = ""
        good = False
        if rep is None:
            got = "НЕ РАСПОЗНАНО"
        elif kind == "url":
            got = OPENED[0] if OPENED else "(ничего не открыто)"
            good = any(expect in u for u in OPENED)
        elif kind == "act":
            got = ", ".join(ACTIONS) or "(нет действия)"
            good = expect in ACTIONS
        elif kind == "confirm":
            got = f"confirm={rep.confirm}"
            good = rep.confirm == expect
        elif kind == "say":
            got = (rep.text or "")[:60]
            good = expect.lower() in (rep.text or "").lower()
        mark = "OK " if good else "FAIL"
        if good:
            ok += 1
        else:
            fail += 1
        print(f"{mark} {phrase:<46} -> {got}")
    print("-" * 110)
    print(f"Успешно: {ok}   Провалено: {fail}   Всего: {ok + fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
