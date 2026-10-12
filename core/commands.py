"""
Действия на компьютере: открыть сайт/программу/папку, поиск, громкость,
скриншот, медиаклавиши, блокировка, выключение и т.д.

Работает на Windows, macOS и Linux — нужная ветка выбирается автоматически.
Опасные действия (выключение, перезагрузка) проходят через подтверждение.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SYSTEM = platform.system()  # Windows / Darwin / Linux
IS_WIN, IS_MAC, IS_LINUX = SYSTEM == "Windows", SYSTEM == "Darwin", SYSTEM == "Linux"


# --------------------------------------------------------------------- ответ


@dataclass
class Reply:
    text: str = ""
    clip_key: str | None = None
    ok: bool = True
    confirm: str | None = None        # id опасного действия, ждущего «да»
    payload: dict = field(default_factory=dict)


# --------------------------------------------------------------------- утилиты


def _popen(cmd, shell=False):
    kwargs = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if IS_WIN:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.Popen(cmd, shell=shell, **kwargs)
        return True
    except Exception as e:
        print(f"[cmd] {cmd}: {e}")
        return False


def _run(cmd, shell=False, timeout=10):
    try:
        kwargs = {}
        if IS_WIN:
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(cmd, shell=shell, capture_output=True, text=True,
                             timeout=timeout, **kwargs)
        return out.returncode == 0, (out.stdout or "").strip()
    except Exception as e:
        return False, str(e)


def _pyautogui():
    try:
        import pyautogui

        pyautogui.FAILSAFE = False
        return pyautogui
    except Exception:
        return None


def norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е").strip()
    s = re.sub(r"[.,!?;:\"'`«»…]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------- каталоги


SITES: dict[str, tuple[str, tuple[str, ...]]] = {
    "google":    ("https://www.google.com",        ("гугл", "гугле", "гуглу", "google", "гуголь")),
    "youtube":   ("https://www.youtube.com",       ("ютуб", "ютубе", "youtube", "ю туб", "ютьюб")),
    "yandex":    ("https://ya.ru",                 ("яндекс", "yandex", "яндекса")),
    "vk":        ("https://vk.com",                ("вконтакте", "вк", "vk", "в контакте")),
    "telegram":  ("https://web.telegram.org",      ("телеграм", "телега", "telegram")),
    "mail":      ("https://mail.google.com",       ("почту", "почта", "гмайл", "gmail", "mail")),
    "wikipedia": ("https://ru.wikipedia.org",      ("википедия", "википедию", "wikipedia", "вики")),
    "github":    ("https://github.com",            ("гитхаб", "гит хаб", "github")),
    "chatgpt":   ("https://chat.openai.com",       ("чатгпт", "чат гпт", "chatgpt", "gpt")),
    "maps":      ("https://www.google.com/maps",   ("карты", "карту", "maps", "гугл карты")),
    "translate": ("https://translate.google.com",  ("переводчик", "перевод", "translate")),
    "twitch":    ("https://www.twitch.tv",         ("твич", "twitch")),
    "spotify":   ("https://open.spotify.com",      ("спотифай", "spotify")),
    "steam":     ("https://store.steampowered.com", ("стим", "steam")),
    "news":      ("https://news.google.com",       ("новости", "news")),
    "weather":   ("https://yandex.ru/pogoda",      ("сайт погоды", "погоду онлайн")),
    "drive":     ("https://drive.google.com",      ("диск", "гугл диск", "drive")),
    "reddit":    ("https://www.reddit.com",        ("реддит", "reddit")),
}

# Программы: ключ -> (Windows, macOS-app, список linux-команд)
APPS: dict[str, tuple[str | None, str | None, tuple[str, ...]]] = {
    "блокнот":            ("notepad",  "TextEdit",          ("gedit", "kate", "mousepad", "xed")),
    "notepad":            ("notepad",  "TextEdit",          ("gedit", "kate", "mousepad", "xed")),
    "калькулятор":        ("calc",     "Calculator",        ("gnome-calculator", "kcalc", "galculator")),
    "calculator":         ("calc",     "Calculator",        ("gnome-calculator", "kcalc", "galculator")),
    "проводник":          ("explorer", "Finder",            ("nautilus", "dolphin", "thunar", "xdg-open")),
    "файлы":              ("explorer", "Finder",            ("nautilus", "dolphin", "thunar", "xdg-open")),
    "explorer":           ("explorer", "Finder",            ("nautilus", "dolphin", "thunar", "xdg-open")),
    "терминал":           ("cmd",      "Terminal",          ("gnome-terminal", "konsole", "xfce4-terminal", "x-terminal-emulator")),
    "командную строку":   ("cmd",      "Terminal",          ("gnome-terminal", "konsole", "x-terminal-emulator")),
    "terminal":           ("cmd",      "Terminal",          ("gnome-terminal", "konsole", "x-terminal-emulator")),
    "paint":              ("mspaint",  None,                ("pinta", "kolourpaint")),
    "паинт":              ("mspaint",  None,                ("pinta", "kolourpaint")),
    "диспетчер задач":    ("taskmgr",  "Activity Monitor",  ("gnome-system-monitor", "ksysguard", "htop")),
    "настройки":          ("ms-settings:", "System Settings", ("gnome-control-center", "systemsettings")),
    "параметры":          ("ms-settings:", "System Settings", ("gnome-control-center", "systemsettings")),
    "ворд":               ("winword",  "Microsoft Word",    ("libreoffice", "--writer")),
    "word":               ("winword",  "Microsoft Word",    ("libreoffice",)),
    "эксель":             ("excel",    "Microsoft Excel",   ("libreoffice",)),
    "excel":              ("excel",    "Microsoft Excel",   ("libreoffice",)),
    "вс код":             ("code",     "Visual Studio Code", ("code", "codium")),
    "вс коде":            ("code",     "Visual Studio Code", ("code", "codium")),
    "vs code":            ("code",     "Visual Studio Code", ("code", "codium")),
    "код":                ("code",     "Visual Studio Code", ("code", "codium")),
    "дискорд":            ("discord",  "Discord",           ("discord",)),
    "discord":            ("discord",  "Discord",           ("discord",)),
    "телеграм приложение": ("telegram", "Telegram",         ("telegram-desktop", "telegram")),
    "стим":               ("steam",    "Steam",             ("steam",)),
    "steam":              ("steam",    "Steam",             ("steam",)),
    "браузер":            (None,       None,                ()),
    "обс":                ("obs64",    "OBS",               ("obs",)),
}

FOLDERS: dict[str, tuple[str, ...]] = {
    "загрузки":   ("Downloads", "Загрузки"),
    "downloads":  ("Downloads", "Загрузки"),
    "документы":  ("Documents", "Документы"),
    "documents":  ("Documents", "Документы"),
    "рабочий стол": ("Desktop", "Рабочий стол"),
    "desktop":    ("Desktop", "Рабочий стол"),
    "изображения": ("Pictures", "Изображения"),
    "картинки":   ("Pictures", "Изображения"),
    "pictures":   ("Pictures", "Изображения"),
    "музыка":     ("Music", "Музыка"),
    "видео":      ("Videos", "Видео"),
    "музыку":     ("Music", "Музыка"),
}


# --------------------------------------------------------------------- действия


def open_url(url: str) -> bool:
    try:
        webbrowser.open(url, new=2)
        return True
    except Exception:
        if IS_WIN:
            return _popen(f'start "" "{url}"', shell=True)
        if IS_MAC:
            return _popen(["open", url])
        return _popen(["xdg-open", url])


def open_path(path: Path) -> bool:
    try:
        if IS_WIN:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        if IS_MAC:
            return _popen(["open", str(path)])
        return _popen(["xdg-open", str(path)])
    except Exception:
        return False


def launch_app(key: str) -> bool:
    win, mac, lin = APPS.get(key, (None, None, ()))
    if key == "браузер":
        return open_url("https://www.google.com")
    if IS_WIN and win:
        if win.endswith(":"):
            return _popen(f"start {win}", shell=True)
        try:
            os.startfile(win)  # type: ignore[attr-defined]
            return True
        except Exception:
            return _popen(f'start "" "{win}"', shell=True)
    if IS_MAC and mac:
        return _popen(["open", "-a", mac])
    if IS_LINUX:
        for c in lin:
            if c.startswith("--"):
                continue
            if shutil.which(c):
                if c == "xdg-open":
                    return _popen([c, str(Path.home())])
                return _popen([c])
    return False


def user_folder(names: tuple[str, ...]) -> Path | None:
    home = Path.home()
    for n in names:
        p = home / n
        if p.exists():
            return p
    return home if home.exists() else None


def set_volume(direction: str, step: int = 10) -> bool:
    """direction: up | down | mute"""
    if IS_MAC:
        if direction == "mute":
            return _run(["osascript", "-e", "set volume output muted not (output muted of (get volume settings))"])[0]
        ok, cur = _run(["osascript", "-e", "output volume of (get volume settings)"])
        try:
            v = int(cur)
        except Exception:
            v = 50
        v = max(0, min(100, v + step if direction == "up" else v - step))
        return _run(["osascript", "-e", f"set volume output volume {v}"])[0]

    if IS_LINUX:
        if shutil.which("pactl"):
            if direction == "mute":
                return _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])[0]
            sign = "+" if direction == "up" else "-"
            return _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{step}%"])[0]
        if shutil.which("amixer"):
            if direction == "mute":
                return _run(["amixer", "-q", "sset", "Master", "toggle"])[0]
            sign = "+" if direction == "up" else "-"
            return _run(["amixer", "-q", "sset", "Master", f"{step}%{sign}"])[0]

    pg = _pyautogui()
    if pg:
        try:
            if direction == "mute":
                pg.press("volumemute")
            else:
                pg.press("volumeup" if direction == "up" else "volumedown",
                         presses=max(1, step // 2), interval=0.02)
            return True
        except Exception:
            pass

    if IS_WIN:
        code = {"up": 175, "down": 174, "mute": 173}[direction]
        n = max(1, step // 2) if direction != "mute" else 1
        ps = ("$w = New-Object -ComObject WScript.Shell; "
              + f"1..{n} | ForEach-Object {{ $w.SendKeys([char]{code}) }}")
        return _run(["powershell", "-NoProfile", "-Command", ps])[0]
    return False


def media_key(key: str) -> bool:
    """key: playpause | next | prev | stop"""
    mapping = {"playpause": "playpause", "next": "nexttrack",
               "prev": "prevtrack", "stop": "stop"}
    pg = _pyautogui()
    if pg:
        try:
            pg.press(mapping.get(key, "playpause"))
            return True
        except Exception:
            pass
    if IS_MAC:
        code = {"playpause": 16, "next": 17, "prev": 18}.get(key, 16)
        return _run(["osascript", "-e",
                     f'tell application "System Events" to key code {code}'])[0]
    if IS_LINUX and shutil.which("playerctl"):
        sub = {"playpause": "play-pause", "next": "next", "prev": "previous", "stop": "stop"}
        return _run(["playerctl", sub.get(key, "play-pause")])[0]
    if IS_WIN:
        code = {"playpause": 179, "next": 176, "prev": 177, "stop": 178}.get(key, 179)
        return _run(["powershell", "-NoProfile", "-Command",
                     f"(New-Object -ComObject WScript.Shell).SendKeys([char]{code})"])[0]
    return False


def screenshot() -> Path | None:
    folder = user_folder(("Pictures", "Изображения")) or Path.home()
    folder = folder / "JarvisShots"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"shot_{datetime.now():%Y-%m-%d_%H-%M-%S}.png"

    pg = _pyautogui()
    if pg:
        try:
            pg.screenshot(str(target))
            if target.exists():
                return target
        except Exception:
            pass
    if IS_MAC:
        if _run(["screencapture", "-x", str(target)])[0] and target.exists():
            return target
    if IS_LINUX:
        for tool, args in (("gnome-screenshot", ["-f", str(target)]),
                           ("spectacle", ["-b", "-n", "-o", str(target)]),
                           ("scrot", [str(target)]),
                           ("import", ["-window", "root", str(target)])):
            if shutil.which(tool) and _run([tool] + args, timeout=20)[0] and target.exists():
                return target
    if IS_WIN:
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
            "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; "
            "$g=[System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); "
            f"$bmp.Save('{target}');"
        )
        if _run(["powershell", "-NoProfile", "-Command", ps], timeout=25)[0] and target.exists():
            return target
    return None


def lock_screen() -> bool:
    if IS_WIN:
        return _popen("rundll32.exe user32.dll,LockWorkStation", shell=True)
    if IS_MAC:
        return _run(["pmset", "displaysleepnow"])[0]
    for cmd in (["loginctl", "lock-session"], ["xdg-screensaver", "lock"],
                ["gnome-screensaver-command", "-l"]):
        if shutil.which(cmd[0]) and _run(cmd)[0]:
            return True
    return False


def sleep_pc() -> bool:
    if IS_WIN:
        return _popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
    if IS_MAC:
        return _run(["pmset", "sleepnow"])[0]
    return _run(["systemctl", "suspend"])[0]


def shutdown_pc(delay: int = 20) -> bool:
    if IS_WIN:
        return _popen(f"shutdown /s /t {delay}", shell=True)
    if IS_MAC:
        return _run(["osascript", "-e", 'tell app "System Events" to shut down'])[0]
    return _run(["shutdown", "-h", f"+{max(1, delay // 60)}"])[0] or _run(["systemctl", "poweroff"])[0]


def reboot_pc(delay: int = 20) -> bool:
    if IS_WIN:
        return _popen(f"shutdown /r /t {delay}", shell=True)
    if IS_MAC:
        return _run(["osascript", "-e", 'tell app "System Events" to restart'])[0]
    return _run(["systemctl", "reboot"])[0]


def cancel_shutdown() -> bool:
    if IS_WIN:
        return _popen("shutdown /a", shell=True)
    return _run(["shutdown", "-c"])[0]


def minimize_all() -> bool:
    if IS_WIN:
        return _run(["powershell", "-NoProfile", "-Command",
                     "(New-Object -ComObject Shell.Application).MinimizeAll()"])[0]
    if IS_MAC:
        return _run(["osascript", "-e",
                     'tell application "System Events" to key code 103'])[0]
    if shutil.which("wmctrl"):
        return _run(["wmctrl", "-k", "on"])[0]
    pg = _pyautogui()
    if pg:
        try:
            pg.hotkey("super", "d")
            return True
        except Exception:
            pass
    return False


def close_window() -> bool:
    pg = _pyautogui()
    if pg:
        try:
            pg.hotkey("command", "w") if IS_MAC else pg.hotkey("alt", "f4")
            return True
        except Exception:
            pass
    return False


def type_text(text: str) -> bool:
    """Печатает текст в активное окно через буфер обмена (надёжно для кириллицы)."""
    pg = _pyautogui()
    try:
        import tkinter as tk

        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.after(400, r.destroy)
        r.mainloop()
    except Exception:
        return False
    if pg:
        try:
            import time as _t

            _t.sleep(0.3)
            pg.hotkey("command", "v") if IS_MAC else pg.hotkey("ctrl", "v")
            return True
        except Exception:
            pass
    return True  # хотя бы в буфере


# --------------------------------------------------------------------- резолвер «открой X»


def resolve_and_open(target: str, cfg: dict) -> Reply:
    t = norm(target)
    t = re.sub(r"^(?:мне|пожалуйста|приложение|программу|сайт|папку|please|the|app)\s+", "", t)
    t = re.sub(r"\s+(?:пожалуйста|please)$", "", t).strip()
    if not t:
        return Reply("Что именно открыть, сэр?", ok=False)

    # 1. пользовательские сайты и программы из config.json
    for name, url in (cfg.get("custom_sites") or {}).items():
        if norm(name) in t:
            return Reply(f"Открываю {name}.", "ack") if open_url(url) \
                else Reply(f"Не удалось открыть {name}.", ok=False)
    for name, path in (cfg.get("custom_apps") or {}).items():
        if norm(name) in t:
            ok = open_path(Path(path)) if Path(path).exists() else _popen(f'start "" "{path}"', shell=True)
            return Reply(f"Запускаю {name}.", "ack") if ok \
                else Reply(f"Не удалось запустить {name}.", ok=False)

    # 2. известные сайты
    for key, (url, aliases) in SITES.items():
        if t == key or t in aliases or any(a == t or t.startswith(a + " ") or t.endswith(" " + a)
                                           for a in aliases):
            return Reply(f"Открываю {key}.", "ack") if open_url(url) \
                else Reply(f"Не удалось открыть {key}.", ok=False)

    # 3. программы
    for key in APPS:
        if t == key or t.startswith(key + " ") or t.endswith(" " + key):
            if launch_app(key):
                return Reply(f"Запускаю {key}.", "ack")
            return Reply(f"Не нашёл программу «{key}» в системе, сэр.", ok=False)

    # 4. папки
    for key, names in FOLDERS.items():
        if key in t:
            folder = user_folder(names)
            if folder and open_path(folder):
                return Reply(f"Открываю папку {key}.", "ack")
            return Reply(f"Папка «{key}» не найдена.", ok=False)

    # 5. похоже на адрес сайта
    if re.match(r"^[\w\-]+\.(ru|com|org|net|io|dev|me|tv|рф|ua|by|kz|info|co)\b", t.replace(" ", "")):
        url = "https://" + t.replace(" ", "")
        return Reply(f"Открываю {t}.", "ack") if open_url(url) else Reply("Не вышло.", ok=False)

    # 6. попытка запустить как системную команду
    exe = t.split()[0]
    if shutil.which(exe):
        if _popen([exe]):
            return Reply(f"Запускаю {exe}.", "ack")
    if IS_WIN and _popen(f'start "" "{t}"', shell=True):
        return Reply(f"Пробую открыть {t}.", "ack")

    # 7. последний шанс — поиск
    url = cfg.get("default_search", "https://www.google.com/search?q={q}").replace(
        "{q}", urllib.parse.quote_plus(target))
    open_url(url)
    return Reply(f"Не нашёл такой программы, сэр. Ищу «{target}» в интернете.")


# --------------------------------------------------------------------- маршрутизатор


OPEN_RE = re.compile(
    r"^(?:открой|открыть|откройка|запусти|запустить|включи|включить|покажи|перейди в|зайди в|"
    r"open|launch|start|run|go to)\s+(?P<what>.+)$")

GOOGLE_RE = re.compile(
    r"^(?:загугли|погугли|нагугли|гугли|google)\s+(?P<q>.+)$")

SEARCH_IN_RE = re.compile(
    r"^(?:найди|поищи|найти|поиск|ищи|search(?:\s+for)?|find)\s+"
    r"(?:(?:в|на)\s+)?(?P<where>гугле|гугл|google|ютубе|ютуб|youtube|яндексе|яндекс|yandex|"
    r"интернете|сети|википедии|wikipedia)\s+(?P<q>.+)$")

SEARCH_TAIL_RE = re.compile(
    r"^(?:найди|поищи|найти|ищи|search|find)\s+(?P<q>.+?)\s+(?:в|на|in|on)\s+"
    r"(?P<where>гугле|google|ютубе|youtube|яндексе|yandex|википедии|wikipedia)$")

SEARCH_RE = re.compile(r"^(?:найди|поищи|найти|ищи|search(?:\s+for)?|find)\s+(?P<q>.+)$")

PLAY_RE = re.compile(
    r"^(?:включи|поставь|запусти|play)\s+(?:видео|музыку|песню|трек|клип|song|music|video)?\s*(?P<q>.+)$")

TYPE_RE = re.compile(r"^(?:напечатай|напиши|введи|type|write)\s+(?P<t>.+)$")


def _search_url(where: str, q: str, cfg: dict) -> tuple[str, str]:
    q_enc = urllib.parse.quote_plus(q)
    where = norm(where)
    if where in ("ютубе", "ютуб", "youtube"):
        return f"https://www.youtube.com/results?search_query={q_enc}", "YouTube"
    if where in ("яндексе", "яндекс", "yandex"):
        return f"https://yandex.ru/search/?text={q_enc}", "Яндексе"
    if where in ("википедии", "wikipedia"):
        return f"https://ru.wikipedia.org/w/index.php?search={q_enc}", "Википедии"
    return cfg.get("default_search", "https://www.google.com/search?q={q}").replace("{q}", q_enc), "Google"


def handle(text: str, lang: str, cfg: dict) -> Reply | None:
    """Пытается выполнить команду. None — команда не распознана этим модулем."""
    t = norm(text)
    if not t:
        return None

    # ---------- поиск ----------
    m = GOOGLE_RE.match(t)
    if m:
        url, name = _search_url("google", m.group("q"), cfg)
        open_url(url)
        return Reply(f"Ищу «{m.group('q')}» в {name}.", "ack")

    m = SEARCH_IN_RE.match(t) or SEARCH_TAIL_RE.match(t)
    if m:
        q = re.sub(r"^(?:for|про|о|об)\s+", "", m.group("q")).strip()
        url, name = _search_url(m.group("where"), q, cfg)
        open_url(url)
        return Reply(f"Ищу «{q}» в {name}.", "ack")

    # ---------- включи музыку/видео на ютубе ----------
    m = re.match(r"^(?:включи|поставь|найди|запусти)\s+(?:на\s+)?(?:ютубе?|youtube)\s+(?P<q>.+)$", t)
    if m:
        url, _ = _search_url("youtube", m.group("q"), cfg)
        open_url(url)
        return Reply(f"Включаю «{m.group('q')}» на YouTube.", "ack")

    m = re.match(r"^(?:включи|поставь|play)\s+(?:видео|музыку|песню|трек|клип|music|song)\s+(?P<q>.+)$", t)
    if m:
        url, _ = _search_url("youtube", m.group("q"), cfg)
        open_url(url)
        return Reply(f"Включаю «{m.group('q')}».", "ack")

    if re.fullmatch(r"(?:включи|поставь)\s+(?:музыку|music)", t):
        open_url("https://www.youtube.com/playlist?list=PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI")
        return Reply("Включаю музыку.", "ack")

    # ---------- громкость ----------
    if re.search(r"(громкость|звук|volume)", t):
        if re.search(r"(выключи|отключи|убери|mute|заглуши|без звука)", t):
            return Reply("Звук выключен.", "done") if set_volume("mute") else Reply("Не получилось, сэр.", ok=False)
        if re.search(r"(больше|выше|прибавь|увеличь|громче|up|louder|поднят)", t):
            return Reply("Прибавляю громкость.", "ack") if set_volume("up", 15) else Reply("Не получилось.", ok=False)
        if re.search(r"(меньше|ниже|убавь|уменьш|тише|down|quieter|понизь)", t):
            return Reply("Убавляю громкость.", "ack") if set_volume("down", 15) else Reply("Не получилось.", ok=False)
    if re.fullmatch(r"(?:сделай\s+|поставь\s+|включи\s+)?(?:по)?тише|quieter|turn it down", t):
        set_volume("down", 15)
        return Reply("Убавляю, сэр.", "ack")
    if re.fullmatch(r"(?:сделай\s+|поставь\s+|включи\s+)?(?:по)?громче|louder|turn it up", t):
        set_volume("up", 15)
        return Reply("Прибавляю, сэр.", "ack")
    if re.fullmatch(r"(?:убавь|приглуши|потиши)(?:\s+\w+)?", t):
        set_volume("down", 15)
        return Reply("Убавляю, сэр.", "ack")
    if re.fullmatch(r"(?:прибавь|поддай)(?:\s+\w+)?", t):
        set_volume("up", 15)
        return Reply("Прибавляю, сэр.", "ack")

    # ---------- медиа ----------
    if re.search(r"(пауза|поставь на паузу|продолжи воспроизведение|pause|resume)", t):
        media_key("playpause")
        return Reply("Готово.", "done")
    if re.search(r"(следующ\w+ (?:трек|песн|видео)|next track|переключи песню|дальше трек)", t):
        media_key("next")
        return Reply("Следующий трек.", "ack")
    if re.search(r"(предыдущ\w+ (?:трек|песн)|previous track)", t):
        media_key("prev")
        return Reply("Предыдущий трек.", "ack")

    # ---------- скриншот ----------
    if re.search(r"(скриншот|снимок экрана|сфотографируй экран|screenshot|screen shot)", t):
        p = screenshot()
        if p:
            return Reply(f"Снимок экрана сохранён: {p.name}", "done", payload={"path": str(p)})
        return Reply("Не удалось сделать скриншот, сэр. Нужен пакет pyautogui.", ok=False)

    # ---------- окна ----------
    if re.search(r"(сверни (?:все|всё)|свернуть все|покажи рабочий стол|minimize all|show desktop)", t):
        minimize_all()
        return Reply("Готово.", "done")
    if re.search(r"(закрой окно|закрыть окно|close window)", t):
        close_window()
        return Reply("Окно закрыто.", "done")

    # ---------- блокировка / питание ----------
    if re.search(r"(заблокируй|блокировка экрана|lock (?:the )?(?:pc|computer|screen))", t):
        return Reply("Блокирую систему.", "ack") if lock_screen() else Reply("Не вышло, сэр.", ok=False)

    if re.search(r"(отмени выключение|отменить выключение|cancel shutdown)", t):
        cancel_shutdown()
        return Reply("Выключение отменено, сэр.", "done")

    if re.search(r"(спящий режим|усыпи|режим сна|sleep mode|перейди в сон)", t):
        return Reply("Перевожу в спящий режим.", "ack") if sleep_pc() else Reply("Не вышло.", ok=False)

    if re.search(r"(выключи компьютер|выключи пк|выключение компьютера|turn off (?:the )?(?:pc|computer)|shut ?down)", t):
        if cfg.get("confirm_dangerous", True):
            return Reply("Выключить компьютер, сэр? Скажите «да» для подтверждения.", confirm="shutdown")
        shutdown_pc()
        return Reply("Выключаюсь через двадцать секунд.", "ack")

    if re.search(r"(перезагрузи|перезапусти компьютер|reboot|restart (?:the )?(?:pc|computer))", t):
        if cfg.get("confirm_dangerous", True):
            return Reply("Перезагрузить компьютер, сэр? Скажите «да» для подтверждения.", confirm="reboot")
        reboot_pc()
        return Reply("Перезагружаюсь.", "ack")

    # ---------- печать текста ----------
    m = TYPE_RE.match(t)
    if m and len(m.group("t")) > 1:
        raw = text.strip()
        payload = re.sub(r"^\s*\S+\s+", "", raw)
        type_text(payload)
        return Reply("Напечатал, сэр.", "done")

    # ---------- открыть что-либо ----------
    m = OPEN_RE.match(t)
    if m:
        return resolve_and_open(m.group("what"), cfg)

    # ---------- «найди ...» без указания места ----------
    m = SEARCH_RE.match(t)
    if m:
        url, name = _search_url("google", m.group("q"), cfg)
        open_url(url)
        return Reply(f"Ищу «{m.group('q')}» в {name}.", "ack")

    return None


def confirm_action(action: str) -> Reply:
    if action == "shutdown":
        shutdown_pc()
        return Reply("Подтверждено. Выключение через двадцать секунд. Скажите «отмени выключение», если передумаете.", "ack")
    if action == "reboot":
        reboot_pc()
        return Reply("Подтверждено. Перезагрузка через двадцать секунд.", "ack")
    return Reply("Действие не найдено.", ok=False)
