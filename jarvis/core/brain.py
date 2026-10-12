"""
«Мозг» Джарвиса — ответы на вопросы без нейросетей и API-ключей.

Умеет:
  • время, дата, день недели, сколько дней до события
  • погода (wttr.in, без ключа)
  • калькулятор, в том числе словами: «сколько будет пятнадцать умножить на семь»
  • краткая справка из Википедии
  • состояние системы: процессор, память, диск, батарея, аптайм
  • таймеры и заметки
  • светская беседа в стиле Джарвиса
"""
from __future__ import annotations

import ast
import json
import math
import operator
import random
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from .commands import Reply, norm
from . import config

# --------------------------------------------------------------------- сеть


def _get(url: str, timeout: float = 6.0) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "JarvisAssistant/1.0 (personal desktop assistant)",
        "Accept-Language": "ru,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# --------------------------------------------------------------------- числа словами


NUM_WORDS = {
    "ноль": 0, "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
    "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
    "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40,
    "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80,
    "девяносто": 90, "сто": 100, "двести": 200, "триста": 300, "четыреста": 400,
    "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800,
    "девятьсот": 900, "тысяча": 1000, "тысячи": 1000,
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

OP_WORDS = [
    (r"\b(?:плюс|прибавить|сложить|и ещё|add|plus)\b", "+"),
    (r"\b(?:минус|вычесть|отнять|minus|subtract)\b", "-"),
    (r"\b(?:умножить на|умножь на|умноженное на|умножить|умножн|times|multiplied by|multiply by)\b", "*"),
    (r"\b(?:разделить на|делить на\s*|поделить на|поделить|разделить|divided by|divide by)\b", "/"),
    (r"\b(?:в степени|степень|to the power of)\b", "**"),
    (r"\b(?:процент(?:ов|а)? от|percent of)\b", "%OF%"),
    (r"\b(?:корень из|квадратный корень из|square root of|sqrt of)\b", "SQRT"),
]


def words_to_expr(s: str) -> str:
    s = norm(s)
    for pat, rep in OP_WORDS:
        s = re.sub(pat, f" {rep} ", s)
    # составные числа: "двадцать пять" -> 25
    tokens = s.split()
    out, buf = [], []

    def flush():
        if buf:
            total, cur = 0, 0
            for v in buf:
                if v >= 1000:
                    cur = (cur or 1) * v
                    total += cur
                    cur = 0
                elif v >= 100:
                    cur += v
                else:
                    cur += v
            out.append(str(total + cur))
            buf.clear()

    for tok in tokens:
        if tok in NUM_WORDS:
            buf.append(NUM_WORDS[tok])
        else:
            flush()
            out.append(tok)
    flush()
    return " ".join(out)


# --------------------------------------------------------------------- калькулятор

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "sin": math.sin, "cos": math.cos,
    "tan": math.tan, "log": math.log, "log10": math.log10, "exp": math.exp,
    "pi": math.pi, "e": math.e, "floor": math.floor, "ceil": math.ceil,
}


def safe_eval(expr: str) -> float:
    def _ev(node):
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("не число")
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_ev(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = _FUNCS.get(node.func.id)
            if callable(fn):
                return fn(*[_ev(a) for a in node.args])
        if isinstance(node, ast.Name) and node.id in _FUNCS:
            v = _FUNCS[node.id]
            if not callable(v):
                return v
        raise ValueError("недопустимое выражение")

    return _ev(ast.parse(expr, mode="eval"))


def fmt_num(v: float) -> str:
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-9:
            return str(int(round(v)))
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def try_math(text: str) -> str | None:
    t = words_to_expr(text)
    t = re.sub(r"^(?:сколько будет|посчитай|вычисли|реши|calculate|compute|what is|whats|how much is)\s+", "", t).strip()
    t = t.replace("x", "*").replace("х", "*").replace("×", "*").replace("÷", "/").replace(",", ".")
    t = t.replace("^", "**")

    m = re.search(r"SQRT\s*([\d.]+)", t)
    if m:
        try:
            return fmt_num(math.sqrt(float(m.group(1))))
        except Exception:
            return None

    m = re.search(r"([\d.]+)\s*%OF%\s*([\d.]+)", t)
    if m:
        try:
            return fmt_num(float(m.group(1)) / 100 * float(m.group(2)))
        except Exception:
            return None
    t = t.replace("%OF%", "*0.01*")

    expr = "".join(ch for ch in t if ch in "0123456789+-*/().% ")
    expr = expr.strip()
    if not expr or not re.search(r"\d", expr):
        return None
    if not re.search(r"[+\-*/%]", expr):
        return None
    try:
        return fmt_num(safe_eval(expr))
    except Exception:
        return None


# --------------------------------------------------------------------- дата/время

WEEKDAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
             "августа", "сентября", "октября", "ноября", "декабря"]


def plural_ru(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def say_time(lang: str) -> str:
    now = datetime.now()
    if lang == "en":
        return f"It is {now.strftime('%H:%M')}, sir."
    h, m = now.hour, now.minute
    return (f"Сейчас {h} {plural_ru(h, ('час', 'часа', 'часов'))} "
            f"{m} {plural_ru(m, ('минута', 'минуты', 'минут'))}, сэр.")


def say_date(lang: str) -> str:
    now = datetime.now()
    if lang == "en":
        return f"Today is {now.strftime('%A, %d %B %Y')}."
    return (f"Сегодня {WEEKDAYS_RU[now.weekday()]}, "
            f"{now.day} {MONTHS_RU[now.month - 1]} {now.year} года.")


# --------------------------------------------------------------------- погода

WEATHER_RU = {
    "sunny": "солнечно", "clear": "ясно", "partly cloudy": "переменная облачность",
    "cloudy": "облачно", "overcast": "пасмурно", "mist": "дымка", "fog": "туман",
    "patchy rain nearby": "местами дождь", "light rain": "небольшой дождь",
    "moderate rain": "дождь", "heavy rain": "сильный дождь", "light snow": "небольшой снег",
    "moderate snow": "снег", "heavy snow": "сильный снег", "thundery outbreaks possible": "возможна гроза",
    "patchy light rain": "небольшой дождь", "light drizzle": "морось",
}


def weather(city: str, lang: str) -> str:
    city_q = urllib.parse.quote(city)
    try:
        raw = _get(f"https://wttr.in/{city_q}?format=j1", timeout=8)
        data = json.loads(raw)
        cur = data["current_condition"][0]
        temp = int(cur["temp_C"])
        feels = int(cur["FeelsLikeC"])
        desc_en = cur["weatherDesc"][0]["value"].strip()
        wind = cur["windspeedKmph"]
        hum = cur["humidity"]
        if lang == "en":
            return (f"In {city} it is {temp} degrees, feels like {feels}. "
                    f"{desc_en}. Wind {wind} kilometres per hour, humidity {hum} percent.")
        desc = WEATHER_RU.get(desc_en.lower(), desc_en)
        return (f"В городе {city} сейчас {temp} "
                f"{plural_ru(temp, ('градус', 'градуса', 'градусов'))}, ощущается как {feels}. "
                f"{desc.capitalize()}. Ветер {wind} километров в час, влажность {hum} процентов.")
    except Exception:
        return ("Не удалось получить погоду, сэр — похоже, нет связи."
                if lang == "ru" else "I could not reach the weather service, sir.")


# --------------------------------------------------------------------- Википедия


def wiki(query: str, lang: str) -> str:
    code = "ru" if lang == "ru" else "en"
    q = query.strip().strip("?")
    try:
        srch = _get(f"https://{code}.wikipedia.org/w/api.php?action=opensearch&limit=1"
                    f"&namespace=0&format=json&search={urllib.parse.quote(q)}", timeout=7)
        arr = json.loads(srch)
        if not arr[1]:
            raise ValueError("пусто")
        title = arr[1][0]
        raw = _get(f"https://{code}.wikipedia.org/api/rest_v1/page/summary/"
                   f"{urllib.parse.quote(title.replace(' ', '_'))}", timeout=7)
        data = json.loads(raw)
        extract = (data.get("extract") or "").strip()
        if not extract:
            raise ValueError("нет текста")
        sentences = re.split(r"(?<=[.!?])\s+", extract)
        short = " ".join(sentences[:3])
        return short[:700]
    except Exception:
        return ("Не нашёл информации, сэр. Возможно, нет связи с Википедией."
                if lang == "ru" else "I could not find anything on that, sir.")


# --------------------------------------------------------------------- система


def system_status(lang: str) -> str:
    try:
        import psutil
    except Exception:
        return ("Модуль psutil не установлен, сэр. Введите: pip install psutil"
                if lang == "ru" else "psutil is not installed, sir.")
    cpu = psutil.cpu_percent(interval=0.6)
    mem = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage(str(config.APP_DIR.anchor or "/"))
        disk_s = f"{disk.percent:.0f}"
    except Exception:
        disk_s = "?"
    up = timedelta(seconds=int(time.time() - psutil.boot_time()))
    hours = up.days * 24 + up.seconds // 3600
    mins = (up.seconds % 3600) // 60
    batt_s = ""
    try:
        b = psutil.sensors_battery()
        if b:
            batt_s = (f" Батарея {int(b.percent)} процентов"
                      + (", заряжается." if b.power_plugged else ".")) if lang == "ru" else \
                     f" Battery at {int(b.percent)} percent."
    except Exception:
        pass
    if lang == "en":
        return (f"All systems nominal, sir. CPU load {cpu:.0f} percent, memory "
                f"{mem.percent:.0f} percent of {mem.total / 1024**3:.1f} gigabytes, disk {disk_s} percent. "
                f"Uptime {hours} hours {mins} minutes.{batt_s}")
    return (f"Все системы в норме, сэр. Загрузка процессора {cpu:.0f} процентов, "
            f"память занята на {mem.percent:.0f} процентов из "
            f"{mem.total / 1024**3:.1f} гигабайт, диск заполнен на {disk_s} процентов. "
            f"Система работает {hours} ч {mins} мин.{batt_s}")


# --------------------------------------------------------------------- таймеры и заметки


class Timers:
    def __init__(self, on_fire=None):
        self.on_fire = on_fire or (lambda label: None)
        self.items: list[dict] = []

    def add(self, seconds: int, label: str = ""):
        fire_at = time.time() + seconds
        item = {"at": fire_at, "label": label}
        self.items.append(item)

        def _t():
            time.sleep(max(0, seconds))
            if item in self.items:
                self.items.remove(item)
                self.on_fire(label)

        threading.Thread(target=_t, daemon=True).start()

    def clear(self):
        self.items.clear()


def parse_duration(t: str) -> int | None:
    t = words_to_expr(t)
    total = 0
    found = False
    for pat, mult in ((r"(\d+)\s*(?:час|часа|часов|ч|hours?|h)\b", 3600),
                      (r"(\d+)\s*(?:минут|минуты|минуту|мин|minutes?|min|m)\b", 60),
                      (r"(\d+)\s*(?:секунд|секунды|секунду|сек|seconds?|sec|s)\b", 1)):
        for m in re.finditer(pat, t):
            total += int(m.group(1)) * mult
            found = True
    if not found:
        m = re.search(r"(\d+)", t)
        if m:
            return int(m.group(1)) * 60
        return None
    return total


def add_note(text: str) -> bool:
    try:
        with open(config.NOTES_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M}] {text}\n")
        return True
    except Exception:
        return False


def read_notes(limit: int = 5) -> list[str]:
    try:
        with open(config.NOTES_PATH, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        return lines[-limit:]
    except Exception:
        return []


# --------------------------------------------------------------------- светская беседа

SMALLTALK_RU = {
    r"^(?:привет|здравствуй|здравствуйте|хай|доброе утро|добрый день|добрый вечер|здарова)\b": [
        "Добрый день, сэр. Чем могу быть полезен?",
        "Здравствуйте, сэр. Все системы готовы к работе.",
        "К вашим услугам, сэр.",
    ],
    r"(?:как дела|как ты|как сам|как настроение)": [
        "Все системы функционируют в штатном режиме, сэр. Благодарю за беспокойство.",
        "Работаю на полную мощность, сэр. А как ваши дела?",
    ],
    r"(?:кто ты|что ты такое|как тебя зовут|твоё имя|твое имя|представься)": [
        "Я Джарвис — ваша интеллектуальная система управления компьютером, сэр.",
        "Джарвис, сэр. Всегда к вашим услугам.",
    ],
    r"(?:что ты умеешь|твои возможности|помощь|помоги|команды|что можешь)": ["__HELP__"],
    r"(?:спасибо|благодарю|спс|мерси)": [
        "Всегда пожалуйста, сэр.",
        "Рад служить, сэр.",
        "Это моя работа, сэр.",
    ],
    r"(?:расскажи анекдот|пошути|шутка|анекдот)": [
        "Сэр, я бы пошутил про рекурсию, но сначала нужно пошутить про рекурсию.",
        "Два байта встретились. Один спрашивает: «Что с тобой?» Второй: «Кажется, у меня чётность барахлит».",
        "Я бы рассказал анекдот про UDP, но нет гарантии, что он до вас дойдёт.",
        "Сэр, мой юмор работает в экспериментальном режиме. Как и ваш режим сна.",
    ],
    r"(?:ты меня слышишь|ты тут|ты здесь|ты живой)": [
        "Я всегда на связи, сэр.",
        "Слышу вас отчётливо, сэр.",
    ],
    r"(?:я тебя люблю|ты лучший|молодец|хороший мальчик)": [
        "Очень признателен, сэр. Постараюсь не разочаровать.",
    ],
    r"(?:подбрось монетку|орёл или решка|монетка)": ["__COIN__"],
    r"(?:кинь кубик|брось кубик|кубик)": ["__DICE__"],
}

SMALLTALK_EN = {
    r"^(?:hi|hello|hey|good morning|good evening|good afternoon)\b": [
        "Good day, sir. How may I assist you?",
        "At your service, sir.",
    ],
    r"(?:how are you|how do you do)": [
        "All systems are functioning within normal parameters, sir.",
    ],
    r"(?:who are you|what is your name|introduce yourself)": [
        "I am Jarvis, your personal computer interface, sir.",
    ],
    r"(?:what can you do|help|your commands|capabilities)": ["__HELP__"],
    r"(?:thank you|thanks|cheers)": ["Always a pleasure, sir.", "My pleasure, sir."],
    r"(?:tell me a joke|joke)": [
        "I would tell you a UDP joke, sir, but you might not get it.",
        "There are ten kinds of people, sir: those who understand binary and those who do not.",
    ],
    r"(?:flip a coin|coin toss)": ["__COIN__"],
    r"(?:roll a die|roll a dice)": ["__DICE__"],
}

HELP_RU = """Вот что я умею, сэр:

ОТКРЫТЬ И ЗАПУСТИТЬ
  • «Джарвис, открой гугл / ютуб / вк / почту»
  • «Джарвис, открой блокнот / калькулятор / проводник / терминал»
  • «Джарвис, открой папку загрузки»
  • «Джарвис, найди в гугле рецепт плова»
  • «Джарвис, включи на ютубе AC/DC»

УПРАВЛЕНИЕ КОМПЬЮТЕРОМ
  • «Джарвис, громкость больше / тише / выключи звук»
  • «Джарвис, сделай скриншот»
  • «Джарвис, сверни все окна», «закрой окно»
  • «Джарвис, пауза», «следующий трек»
  • «Джарвис, заблокируй компьютер»
  • «Джарвис, выключи компьютер» (спросит подтверждение)

ВОПРОСЫ
  • «Джарвис, который час?», «какое сегодня число?»
  • «Джарвис, какая погода?»
  • «Джарвис, сколько будет 15 умножить на 7?»
  • «Джарвис, что такое квазар?»
  • «Джарвис, состояние системы»

ПРОЧЕЕ
  • «Джарвис, поставь таймер на 10 минут»
  • «Джарвис, запиши заметку купить хлеб», «прочитай заметки»
  • «Джарвис, подбрось монетку»
  • «Джарвис, стоп» — прервать речь"""

HELP_EN = """Here is what I can do, sir:

  • "Jarvis, open google / youtube / notepad / calculator"
  • "Jarvis, search google for pasta recipe"
  • "Jarvis, volume up / down / mute"
  • "Jarvis, take a screenshot"
  • "Jarvis, lock the computer"
  • "Jarvis, what time is it?" / "what's the date?"
  • "Jarvis, what's the weather?"
  • "Jarvis, what is 15 times 7?"
  • "Jarvis, what is a quasar?"
  • "Jarvis, system status"
  • "Jarvis, set a timer for 10 minutes"
  • "Jarvis, stop" """


# --------------------------------------------------------------------- маршрутизатор


def handle(text: str, lang: str, cfg: dict, timers: "Timers | None" = None) -> Reply | None:
    t = norm(text)
    if not t:
        return None

    # ---------- время и дата ----------
    if re.search(r"(который час|сколько времени|текущее время|what time|time is it)", t):
        return Reply(say_time(lang))
    if re.search(r"(какое (?:сегодня )?(?:число|сегодня дата)|какой сегодня день|сегодняшняя дата|"
                 r"what(?:'s| is) the date|what day is it|какое сегодня)", t):
        return Reply(say_date(lang))
    if re.search(r"(какой сейчас год|what year)", t):
        return Reply(f"Сейчас {datetime.now().year} год, сэр." if lang == "ru"
                     else f"It is {datetime.now().year}, sir.")

    # ---------- погода ----------
    m = re.search(r"погод\w*(?:\s+в\s+(?P<city>[\w\s-]+))?", t) or \
        re.search(r"weather(?:\s+in\s+(?P<city>[\w\s-]+))?", t)
    if m:
        city = (m.groupdict().get("city") or "").strip() or cfg.get("city", "Москва")
        city = re.sub(r"\s+(?:сейчас|сегодня|today|now)$", "", city).strip()
        return Reply(weather(city, lang))

    # ---------- состояние системы ----------
    if re.search(r"(состояние системы|статус системы|загрузка процессора|сколько памяти|"
                 r"system status|cpu load|диагностик)", t):
        return Reply(system_status(lang))

    # ---------- таймер ----------
    m = re.search(r"(?:поставь|заведи|включи|set)\s+(?:таймер|будильник|timer)\s*(?:на|for)?\s*(?P<d>.+)", t)
    if m and timers is not None:
        secs = parse_duration(m.group("d"))
        if secs and secs > 0:
            timers.add(secs, m.group("d").strip())
            mins = secs // 60
            if lang == "en":
                return Reply(f"Timer set for {mins} minutes, sir.", "done")
            if mins >= 1:
                return Reply(f"Таймер на {mins} {plural_ru(mins, ('минуту', 'минуты', 'минут'))} установлен, сэр.", "done")
            return Reply(f"Таймер на {secs} секунд установлен, сэр.", "done")
        return Reply("Не понял, на какое время ставить таймер, сэр.", ok=False)

    # ---------- заметки ----------
    m = re.search(r"(?:запиши|сохрани|добавь)\s+(?:заметку|запись|note)\s+(?P<n>.+)", norm(text))
    if m:
        raw = re.sub(r"^.*?(?:заметку|запись|note)\s+", "", text.strip(), flags=re.I)
        return Reply("Записал, сэр.", "done") if add_note(raw) else Reply("Не смог записать, сэр.", ok=False)
    if re.search(r"(прочитай заметки|мои заметки|покажи заметки|read notes)", t):
        notes = read_notes()
        if not notes:
            return Reply("Заметок пока нет, сэр." if lang == "ru" else "No notes yet, sir.")
        body = "\n".join(notes)
        spoken = "Ваши последние заметки: " + "; ".join(
            re.sub(r"^\[.*?\]\s*", "", n) for n in notes)
        return Reply(spoken, payload={"display": body})

    # ---------- калькулятор ----------
    if re.search(r"(сколько будет|посчитай|вычисли|реши|calculate|what is \d|how much is)", t) or \
       re.fullmatch(r"[\d\s+\-*/().,^х×÷]+", t):
        res = try_math(text)
        if res is not None:
            return Reply(f"Получается {res}, сэр." if lang == "ru" else f"That is {res}, sir.")

    # ---------- светская беседа ----------
    table = SMALLTALK_EN if lang == "en" else SMALLTALK_RU
    for pat, answers in table.items():
        if re.search(pat, t):
            ans = random.choice(answers)
            if ans == "__HELP__":
                h = HELP_EN if lang == "en" else HELP_RU
                return Reply("Вот мои основные возможности, сэр. Список на экране."
                             if lang == "ru" else "Here are my capabilities, sir.",
                             payload={"display": h})
            if ans == "__COIN__":
                side = random.choice(["орёл", "решка"] if lang == "ru" else ["heads", "tails"])
                return Reply(f"Выпал {side}, сэр." if lang == "ru" else f"It is {side}, sir.")
            if ans == "__DICE__":
                n = random.randint(1, 6)
                return Reply(f"Выпало {n}, сэр." if lang == "ru" else f"You rolled {n}, sir.")
            return Reply(ans)

    # ---------- энциклопедия ----------
    m = re.search(r"^(?:что такое|кто такой|кто такая|кто такие|расскажи (?:про|о|об)|"
                  r"что значит|объясни|who is|what is|what are|tell me about)\s+(?P<q>.+)$", t)
    if m:
        q = m.group("q").strip(" ?")
        return Reply(wiki(q, lang), payload={"display": None})

    # ---------- последняя попытка: чистая математика в тексте ----------
    res = try_math(text)
    if res is not None and re.search(r"\d", t):
        return Reply(f"Получается {res}, сэр." if lang == "ru" else f"That is {res}, sir.")

    return None
