"""
Интерфейс J.A.R.V.I.S. — HUD в стиле Mark II на чистом tkinter.
Никаких внешних зависимостей: работает на любой системе, где есть Python с tkinter.
"""
from __future__ import annotations

import json
import math
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from . import config, speech
from .assistant import Assistant
from .updater import Release, Updater
from .version import __version__

# ------------------------------------------------------------------ палитра
BG = "#05080f"
PANEL = "#0a1424"
PANEL2 = "#081120"
LINE = "#14314a"
CYAN = "#3ad8ff"
CYAN_DIM = "#1d6f8f"
GOLD = "#ffb23f"
RED = "#ff5a5a"
GREEN = "#55e39b"
TEXT = "#cfe8f5"
MUTED = "#5f8197"


def mono(size=10, bold=False):
    for fam in ("Consolas", "JetBrains Mono", "DejaVu Sans Mono", "Menlo", "Courier New"):
        try:
            f = tkfont.Font(family=fam, size=size, weight="bold" if bold else "normal")
            if f.actual("family").lower().replace(" ", "") in fam.lower().replace(" ", ""):
                return f
        except Exception:
            continue
    return tkfont.Font(family="TkFixedFont", size=size, weight="bold" if bold else "normal")


def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1: str, c2: str, t: float) -> str:
    """Плавный переход между двумя цветами (t = 0..1)."""
    t = max(0.0, min(1.0, t))
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ui_font(size=10, bold=False):
    for fam in ("Segoe UI", "SF Pro Text", "Ubuntu", "DejaVu Sans", "Helvetica"):
        try:
            return tkfont.Font(family=fam, size=size, weight="bold" if bold else "normal")
        except Exception:
            continue
    return tkfont.Font(size=size, weight="bold" if bold else "normal")


# ------------------------------------------------------------------ реактор


class Reactor(tk.Canvas):
    """Анимированное ядро: вращающиеся дуги + пульсирующее ядро."""

    def __init__(self, master, size=300, **kw):
        super().__init__(master, width=size, height=size, bg=BG,
                         highlightthickness=0, bd=0, **kw)
        self.size = size
        self.state = "idle"       # idle | listening | thinking | speaking | error
        self.level = 0.0
        self._t = 0.0
        self._running = True
        self._tick()

    def set_state(self, state: str):
        if state != self.state:
            self.state = state

    def _colors(self):
        return {
            "idle": (CYAN_DIM, CYAN_DIM, "#0d2535"),
            "listening": (CYAN, "#9bf0ff", "#0d3f52"),
            "thinking": (GOLD, "#ffd890", "#3a2a0d"),
            "speaking": (GOLD, "#fff0c8", "#4a3410"),
            "error": (RED, "#ffb0b0", "#3a1414"),
        }.get(self.state, (CYAN_DIM, CYAN_DIM, "#0d2535"))

    def _tick(self):
        if not self._running:
            return
        try:
            self._draw()
        except tk.TclError:
            return
        self._t += 0.045
        self.after(33, self._tick)

    def stop(self):
        self._running = False

    def _draw(self):
        self.delete("all")
        s = self.size
        cx = cy = s / 2
        main, bright, glow = self._colors()
        t = self._t

        speed = {"idle": 0.45, "listening": 1.3, "thinking": 2.2, "speaking": 1.8, "error": 0.8}[self.state]
        amp = {"idle": 0.02, "listening": 0.07, "thinking": 0.05, "speaking": 0.10, "error": 0.03}[self.state]
        pulse = 1 + amp * math.sin(t * 3.0 * speed)
        core = s * 0.135 * pulse

        # мягкое свечение под всем остальным
        steps = 9
        for i in range(steps, 0, -1):
            rr = core * (0.9 + 2.3 * i / steps)
            col = mix(BG, glow, (1 - (i - 1) / steps) ** 1.7)
            self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline="", fill=col)

        # внешнее кольцо-шкала
        r0 = s * 0.46
        for i in range(60):
            a = math.radians(i * 6 + t * 8 * speed)
            long_tick = (i % 5 == 0)
            r1 = r0
            r2 = r0 - (10 if long_tick else 5)
            x1, y1 = cx + r1 * math.cos(a), cy + r1 * math.sin(a)
            x2, y2 = cx + r2 * math.cos(a), cy + r2 * math.sin(a)
            self.create_line(x1, y1, x2, y2,
                             fill=bright if long_tick else main,
                             width=2 if long_tick else 1)

        # вращающиеся дуги
        rings = [(0.40, 110, 1.0, 3), (0.345, 70, -1.6, 2), (0.29, 150, 2.1, 2), (0.235, 60, -2.6, 3)]
        for frac, extent, dir_, w in rings:
            r = s * frac * pulse
            start = (t * 55 * speed * dir_) % 360
            self.create_arc(cx - r, cy - r, cx + r, cy + r,
                            start=start, extent=extent, style=tk.ARC,
                            outline=main, width=w)
            self.create_arc(cx - r, cy - r, cx + r, cy + r,
                            start=start + 180, extent=extent * 0.6, style=tk.ARC,
                            outline=bright, width=max(1, w - 1))

        # ядро
        self.create_oval(cx - core * 1.55, cy - core * 1.55, cx + core * 1.55, cy + core * 1.55,
                         outline=main, width=1)
        self.create_oval(cx - core, cy - core, cx + core, cy + core,
                         outline=bright, width=2, fill=mix(glow, bright, 0.25))

        # треугольник-сердечник
        rr = core * 0.6
        pts = []
        for i in range(3):
            a = math.radians(-90 + i * 120 - t * 25 * speed)
            pts += [cx + rr * math.cos(a), cy + rr * math.sin(a)]
        self.create_polygon(pts, outline=bright, fill="", width=2)

        # волна уровня звука
        if self.state in ("listening", "speaking"):
            rr = s * 0.43
            pts = []
            for i in range(0, 361, 6):
                a = math.radians(i)
                w = 1 + 0.035 * math.sin(i * 0.25 + t * 9) * (1 + 2 * self.level)
                pts.append((cx + rr * w * math.cos(a), cy + rr * w * math.sin(a)))
            flat = [c for p in pts for c in p]
            self.create_line(*flat, fill=main, width=1, smooth=True)


# ------------------------------------------------------------------ главное окно


class JarvisApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = config.ensure_exists()
        self.title("J.A.R.V.I.S. — голосовой помощник")
        self.configure(bg=BG)
        self.geometry("1040x700")
        self.minsize(880, 600)

        self._events: "queue.Queue" = queue.Queue()
        self._speaking = False

        self.f_title = ui_font(22, True)
        self.f_sub = ui_font(9)
        self.f_log = mono(10)
        self.f_btn = ui_font(10, True)

        self._build()

        self.assistant = Assistant(
            self.cfg,
            on_event=lambda k, t, e=None: self._events.put((k, t, e)),
            on_speaking=lambda b: self._events.put(("__speaking__", b, None)),
            on_listen_state=lambda s: self._events.put(("__listen__", s, None)),
        )
        self.updater = Updater(self.cfg, on_event=lambda k, t: self._events.put((k, t, None)))
        # голосовая команда «Джарвис, проверь обновления»
        self.assistant.update_handler = lambda: self._check_updates(force=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(60, self._pump)
        self.after(400, self._startup)

    # -------------------------------------------------------------- вёрстка
    def _build(self):
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=14, pady=12)

        # ---------- шапка ----------
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x", pady=(0, 10))
        tk.Label(head, text="J.A.R.V.I.S.", font=self.f_title, fg=CYAN, bg=BG).pack(side="left")
        tk.Label(head, text="  Just A Rather Very Intelligent System",
                 font=self.f_sub, fg=MUTED, bg=BG).pack(side="left", pady=(10, 0))
        self.lbl_clock = tk.Label(head, text="", font=mono(11), fg=MUTED, bg=BG)
        self.lbl_clock.pack(side="right", pady=(8, 0))
        self.lbl_version = tk.Label(head, text=f"v{__version__} ", font=mono(9), fg=MUTED,
                                    bg=BG, cursor="hand2")
        self.lbl_version.pack(side="right", pady=(9, 0))
        self.lbl_version.bind("<Button-1>", lambda e: self._check_updates(force=True))
        for ev, col in (("<Enter>", CYAN), ("<Leave>", MUTED)):
            self.lbl_version.bind(ev, lambda e, c=col: self.lbl_version.config(fg=c))
        self._tick_clock()

        tk.Frame(root, bg=LINE, height=1).pack(fill="x", pady=(0, 10))

        # ---------- баннер обновления (появляется по необходимости) ----------
        self.banner = tk.Frame(root, bg=PANEL2, highlightthickness=1, highlightbackground=GOLD)
        self.banner_label = tk.Label(self.banner, text="", font=ui_font(10, True), fg=GOLD,
                                     bg=PANEL2, anchor="w", justify="left")
        self.banner_label.pack(side="left", padx=12, pady=9)
        self.banner_close = tk.Button(self.banner, text="✕", font=ui_font(9), fg=MUTED, bg=PANEL2,
                                      bd=0, cursor="hand2", activebackground=PANEL2,
                                      command=self._hide_banner)
        self.banner_close.pack(side="right", padx=(4, 10))
        self.banner_btn = tk.Button(self.banner, text="", font=ui_font(9, True), fg=BG, bg=GOLD,
                                    bd=0, cursor="hand2", padx=14, pady=4,
                                    activebackground="#ffd38a")
        self.banner_link = tk.Button(self.banner, text="что нового", font=ui_font(9), fg=MUTED,
                                     bg=PANEL2, bd=0, cursor="hand2", activebackground=PANEL2)

        # строка состояния прижата к низу — её не должно выдавливать содержимым
        self.status = tk.Label(root, text="", font=mono(8), fg=MUTED, bg=BG, anchor="w")
        self.status.pack(side="bottom", fill="x", pady=(8, 0))

        body = tk.Frame(root, bg=BG)
        body.pack(side="top", fill="both", expand=True)
        self.body = body

        # ---------- левая колонка ----------
        left = tk.Frame(body, bg=BG, width=330)
        left.pack(side="left", fill="y", padx=(0, 14))
        left.pack_propagate(False)

        self.reactor = Reactor(left, size=300)
        self.reactor.pack(pady=(4, 6))

        self.lbl_state = tk.Label(left, text="РЕЖИМ ОЖИДАНИЯ", font=mono(11, True),
                                  fg=CYAN_DIM, bg=BG)
        self.lbl_state.pack()
        self.lbl_hint = tk.Label(left, text="скажите «Джарвис…» или напишите снизу",
                                 font=self.f_sub, fg=MUTED, bg=BG, wraplength=300)
        self.lbl_hint.pack(pady=(2, 10))

        self.btn_mic = self._button(left, "◉  ВКЛЮЧИТЬ МИКРОФОН", self._toggle_mic, accent=True)
        self.btn_mic.pack(fill="x", pady=3)
        self.btn_once = self._button(left, "◎  СКАЗАТЬ ОДИН РАЗ", self._listen_once)
        self.btn_once.pack(fill="x", pady=3)

        row = tk.Frame(left, bg=BG)
        row.pack(fill="x", pady=3)
        self._button(row, "⚙ НАСТРОЙКИ", self._open_settings).pack(side="left", fill="x", expand=True, padx=(0, 3))
        self._button(row, "✖ СТОП", self._shutup).pack(side="left", fill="x", expand=True, padx=(3, 0))

        # ---------- правая колонка ----------
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        # поле ввода прижато к низу правой колонки
        self.entry_wrap = tk.Frame(right, bg=LINE)
        self.entry_wrap.pack(side="bottom", fill="x", pady=(10, 0))

        logwrap = tk.Frame(right, bg=LINE, bd=0)
        logwrap.pack(side="top", fill="both", expand=True)
        inner = tk.Frame(logwrap, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        bar = tk.Frame(inner, bg=PANEL2)
        bar.pack(fill="x")
        tk.Label(bar, text="  ЖУРНАЛ ДИАЛОГА", font=mono(9, True), fg=CYAN_DIM,
                 bg=PANEL2).pack(side="left", pady=5)
        tk.Button(bar, text="очистить", font=self.f_sub, fg=MUTED, bg=PANEL2,
                  activebackground=PANEL2, activeforeground=CYAN, bd=0,
                  cursor="hand2", command=self._clear_log).pack(side="right", padx=8)

        txtfr = tk.Frame(inner, bg=PANEL)
        txtfr.pack(fill="both", expand=True)
        self.log = tk.Text(txtfr, bg=PANEL, fg=TEXT, font=self.f_log, bd=0, width=20, height=8,
                           wrap="word", padx=12, pady=10, insertbackground=CYAN,
                           selectbackground=CYAN_DIM, state="disabled", spacing1=2, spacing3=4)
        sb = tk.Scrollbar(txtfr, command=self.log.yview, bg=PANEL, troughcolor=PANEL2,
                          bd=0, highlightthickness=0, width=10)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        self.log.tag_config("user", foreground="#9fe8ff", font=mono(10, True), lmargin1=0, lmargin2=16)
        self.log.tag_config("jarvis", foreground=GOLD, lmargin1=0, lmargin2=16)
        self.log.tag_config("system", foreground=MUTED, font=mono(9))
        self.log.tag_config("error", foreground=RED, font=mono(9))
        self.log.tag_config("display", foreground="#bfe3cf", font=mono(9),
                            lmargin1=16, lmargin2=16, background=PANEL2)
        self.log.tag_config("time", foreground="#3a5a6e", font=mono(8))

        # ---------- строка ввода ----------
        ef = tk.Frame(self.entry_wrap, bg=PANEL2)
        ef.pack(fill="x", padx=1, pady=1)
        tk.Label(ef, text=" ❯", font=mono(12, True), fg=CYAN, bg=PANEL2).pack(side="left")
        self.entry = tk.Entry(ef, bg=PANEL2, fg=TEXT, font=mono(11), bd=0, width=10,
                              insertbackground=CYAN, relief="flat")
        self.entry.pack(side="left", fill="x", expand=True, padx=6, pady=9)
        self.entry.bind("<Return>", lambda e: self._send())
        self.entry.bind("<Up>", self._history_up)
        tk.Button(ef, text="ОТПРАВИТЬ", font=self.f_btn, fg=BG, bg=CYAN, bd=0,
                  activebackground="#8ae9ff", cursor="hand2", padx=14,
                  command=self._send).pack(side="right", padx=6, pady=5)

    def _button(self, parent, text, cmd, accent=False):
        return tk.Button(
            parent, text=text, command=cmd, font=self.f_btn,
            fg=BG if accent else CYAN, bg=CYAN if accent else PANEL,
            activebackground="#8ae9ff" if accent else LINE,
            activeforeground=BG if accent else CYAN,
            bd=0, relief="flat", cursor="hand2", pady=9,
            highlightthickness=1, highlightbackground=LINE,
        )

    def _tick_clock(self):
        try:
            self.lbl_clock.config(text=time.strftime("%H:%M:%S   %d.%m.%Y"))
            self.after(1000, self._tick_clock)
        except tk.TclError:
            pass

    # -------------------------------------------------------------- журнал
    def _append(self, kind: str, text: str):
        self.log.config(state="normal")
        stamp = time.strftime("%H:%M:%S")
        if kind == "user":
            self.log.insert("end", f"{stamp}  ", "time")
            self.log.insert("end", f"ВЫ: {text}\n", "user")
        elif kind == "jarvis":
            self.log.insert("end", f"{stamp}  ", "time")
            self.log.insert("end", f"JARVIS: {text}\n", "jarvis")
        elif kind == "display":
            self.log.insert("end", text.rstrip() + "\n", "display")
        elif kind == "error":
            self.log.insert("end", f"{stamp}  ! {text}\n", "error")
        else:
            self.log.insert("end", f"{stamp}  {text}\n", "system")
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    # -------------------------------------------------------------- события
    def _pump(self):
        try:
            while True:
                kind, text, extra = self._events.get_nowait()
                if kind == "__speaking__":
                    self._speaking = bool(text)
                    self._refresh_state()
                elif kind == "__listen__":
                    self._listen_state = text
                    self._refresh_state()
                elif kind == "__release__":
                    self._on_release(text)
                elif kind == "__progress__":
                    pct = float(text) * 100
                    ver = getattr(extra, "version", "")
                    self.banner_label.config(text=f"Загрузка версии {ver}…  {pct:.0f} %")
                elif kind == "__updated__":
                    self._on_updated(bool(text), extra)
                else:
                    self._append(kind, str(text))
        except queue.Empty:
            pass
        except Exception as e:
            print("[ui]", e)
        self.after(60, self._pump)

    _listen_state = "idle"

    def _refresh_state(self):
        if self._speaking:
            self.reactor.set_state("speaking")
            self.lbl_state.config(text="ГОВОРИТ", fg=GOLD)
        elif self._listen_state == "listening":
            self.reactor.set_state("listening")
            self.lbl_state.config(text="СЛУШАЮ…", fg=CYAN)
        elif self._listen_state == "recognizing":
            self.reactor.set_state("thinking")
            self.lbl_state.config(text="РАСПОЗНАЮ…", fg=GOLD)
        elif self._listen_state == "calibrating":
            self.reactor.set_state("thinking")
            self.lbl_state.config(text="НАСТРОЙКА МИКРОФОНА", fg=GOLD)
        elif self._listen_state == "error":
            self.reactor.set_state("error")
            self.lbl_state.config(text="ОШИБКА МИКРОФОНА", fg=RED)
        else:
            self.reactor.set_state("idle")
            self.lbl_state.config(text="РЕЖИМ ОЖИДАНИЯ", fg=CYAN_DIM)

    # -------------------------------------------------------------- действия
    def _startup(self):
        v = self.assistant.voice.status()
        s = speech.diagnostics()
        self.status.config(
            text=f"проигрыватель: {v['player']}   локальный синтез: {v['local_tts']}   "
                 f"клипов RU/EN: {v['clips_ru']}/{v['clips_en']}   "
                 f"распознавание: {s['SpeechRecognition']}   микрофон: {s['микрофон (PyAudio)']}   "
                 f"устройств: {s['микрофонов найдено']}")

        self._append("system", "Система инициализирована. Напишите «помощь» или скажите «Джарвис, что ты умеешь».")
        why = self.assistant.listener.why_unusable()
        if why:
            self._append("error", f"Голосовой ввод недоступен — {why}")
            self._append("system", "Текстовые команды работают: введите их в строку снизу.")
        self.assistant.boot()
        if self.cfg.get("listen_on_launch") and not why:
            self.after(2500, self._toggle_mic)
        if self.cfg.get("update_check_on_start") and (self.cfg.get("update_repo") or "").strip():
            self.after(5000, lambda: self._check_updates(force=False))
        self.entry.focus_set()

    def _toggle_mic(self):
        on = self.assistant.toggle_listening()
        if on:
            self.btn_mic.config(text="■  ВЫКЛЮЧИТЬ МИКРОФОН", bg=GOLD, activebackground="#ffd38a")
            self._append("system", "Микрофон включён. Произнесите: «Джарвис, открой гугл».")
        else:
            self.btn_mic.config(text="◉  ВКЛЮЧИТЬ МИКРОФОН", bg=CYAN, activebackground="#8ae9ff")
            self._append("system", "Микрофон выключен.")
            self._listen_state = "idle"
            self._refresh_state()

    def _listen_once(self):
        def run():
            self._events.put(("system", "Говорите…", None))
            txt = self.assistant.listener.listen_once(timeout=7)
            if txt:
                self.assistant.handle_text(txt)   # без активационного слова
            else:
                self._events.put(("system", "Ничего не расслышал, сэр.", None))
        threading.Thread(target=run, daemon=True).start()

    def _shutup(self):
        self.assistant.voice.shutup()
        self._append("system", "Речь прервана.")

    _hist_idx = 0

    def _history_up(self, _e=None):
        users = [t for k, t in self.assistant.history if k == "user"]
        if not users:
            return
        self._hist_idx = min(self._hist_idx + 1, len(users))
        self.entry.delete(0, "end")
        self.entry.insert(0, users[-self._hist_idx])

    def _send(self):
        txt = self.entry.get().strip()
        if not txt:
            return
        self.entry.delete(0, "end")
        self._hist_idx = 0
        threading.Thread(target=self.assistant.handle_text, args=(txt,), daemon=True).start()

    # -------------------------------------------------------------- обновления
    def _show_banner(self, text, btn_text=None, btn_cmd=None, link_url=None):
        self.banner_label.config(text=text)
        if btn_text:
            self.banner_btn.config(text=btn_text, command=btn_cmd or (lambda: None))
            self.banner_btn.pack(side="right", padx=6, pady=6)
        else:
            self.banner_btn.pack_forget()
        if link_url:
            self.banner_link.config(command=lambda u=link_url: webbrowser.open(u))
            self.banner_link.pack(side="right", padx=6)
        else:
            self.banner_link.pack_forget()
        self.banner.pack(fill="x", pady=(0, 10), before=self.body)

    def _hide_banner(self):
        self.banner.pack_forget()

    def _lang(self) -> str:
        return "en" if self.cfg.get("language") == "en" else "ru"

    def _check_updates(self, force: bool = False):
        repo = (self.cfg.get("update_repo") or "").strip()
        if not repo or "/" not in repo:
            self._append("system", "Чтобы включить автообновление, укажите в настройках "
                                   "репозиторий GitHub в формате «логин/название».")
            if force:
                self._open_settings()
            return
        if self.updater.busy:
            return
        if force:
            self._append("system", f"Проверяю обновления в {repo}…")
        self.updater.check_async(
            lambda rel: self._events.put(("__release__", rel, None)), force=force)

    def _on_release(self, rel: "Release | None"):
        if rel is None:
            return
        self._append("system", f"Доступна версия {rel.version} (у вас {__version__}). "
                               f"Тип установки: {self.updater.describe()}.")
        self.assistant.voice.say(clip_key="update", lang=self._lang())
        if self.cfg.get("update_auto_install"):
            self._do_update(rel)
            return
        self._show_banner(
            f"Доступно обновление — версия {rel.version}"
            + (f" от {rel.published}" if rel.published else "")
            + f".  У вас {__version__}.",
            "ОБНОВИТЬ", lambda r=rel: self._do_update(r), rel.url)

    def _do_update(self, rel: "Release"):
        self._show_banner(f"Загрузка версии {rel.version}…  0 %")
        self.updater.update_now(
            rel,
            progress=lambda f: self._events.put(("__progress__", f, rel)),
            done=lambda ok: self._events.put(("__updated__", ok, rel)),
        )

    def _on_updated(self, ok: bool, rel):
        if not ok:
            self._show_banner("Обновление не установлено. Подробности в журнале.",
                              "ПОПРОБОВАТЬ СНОВА", lambda r=rel: self._do_update(r),
                              rel.url if rel else None)
            return
        self.assistant.voice.say(clip_key="updated", lang=self._lang())
        if self.updater.install_kind() in ("installer", "portable"):
            self._show_banner("Обновление установлено. Приложение сейчас перезапустится.")
            self.after(3500, self._on_close)
        else:
            self._show_banner("Обновление готово. Перезапустите приложение, чтобы применить.")

    # -------------------------------------------------------------- настройки
    def _open_settings(self):
        SettingsWindow(self)

    def _on_close(self):
        try:
            self.reactor.stop()
            self.assistant.shutdown()
        except Exception:
            pass
        self.destroy()


# ------------------------------------------------------------------ настройки


class SettingsWindow(tk.Toplevel):
    def __init__(self, app: JarvisApp):
        super().__init__(app)
        self.app = app
        self.cfg = app.cfg
        self.title("Настройки J.A.R.V.I.S.")
        self.configure(bg=BG)
        self.geometry("620x660")
        self.transient(app)
        self.vars: dict[str, tk.Variable] = {}

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(wrap, text="НАСТРОЙКИ", font=ui_font(15, True), fg=CYAN, bg=BG).pack(anchor="w")
        tk.Frame(wrap, bg=LINE, height=1).pack(fill="x", pady=(6, 10))

        # кнопки закреплены внизу, содержимое прокручивается
        btns = tk.Frame(wrap, bg=BG)
        btns.pack(side="bottom", fill="x", pady=(12, 0))

        scroll_area = tk.Frame(wrap, bg=BG)
        scroll_area.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(scroll_area, bg=BG, highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(scroll_area, orient="vertical", command=canvas.yview,
                           bg=PANEL, troughcolor=BG, bd=0, highlightthickness=0, width=11)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        c = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0, 0), window=c, anchor="nw")
        c.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))

        def _wheel(e):
            delta = -1 * (e.delta // 120) if e.delta else (1 if e.num == 5 else -1)
            canvas.yview_scroll(delta, "units")

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind_all(seq, _wheel)
        self.bind("<Destroy>", lambda e: [canvas.unbind_all(s) for s in
                                          ("<MouseWheel>", "<Button-4>", "<Button-5>")]
                  if e.widget is self else None)

        self._combo(c, "Язык общения", "language",
                    [("авто (русский + английский)", "auto"), ("только русский", "ru"), ("только английский", "en")])
        self._check(c, "Требовать обращение «Джарвис» перед командой", "require_wake_word")
        self._entry(c, "Слова-активаторы (через запятую)", "wake_words", listmode=True)
        self._entry(c, "Город для погоды", "city")

        tk.Frame(c, bg=LINE, height=1).pack(fill="x", pady=10)

        mics = speech.list_microphones()
        mic_opts = [("по умолчанию", "")] + [(f"{i}: {n[:40]}", str(i)) for i, n in enumerate(mics)]
        self._combo(c, "Микрофон", "mic_index", mic_opts, as_int=True)
        self._combo(c, "Движок распознавания", "stt_engine",
                    [("Google (нужен интернет, бесплатно)", "google"), ("Vosk (полностью оффлайн)", "vosk")])
        self._entry(c, "Путь к модели Vosk (если выбран Vosk)", "vosk_model_path")
        self._scale(c, "Чувствительность микрофона (порог)", "energy_threshold", 100, 2000)

        tk.Frame(c, bg=LINE, height=1).pack(fill="x", pady=10)

        self._combo(c, "Голос", "tts_engine",
                    [("клипы Джарвиса + локальный синтез", "auto"),
                     ("только клипы Джарвиса", "clips"),
                     ("только локальный синтез", "pyttsx3"),
                     ("нейросетевой edge-tts (интернет)", "edge")])
        self._entry(c, "Подсказка выбора системного голоса (напр. Pavel)", "tts_voice_hint")
        self._scale(c, "Скорость речи", "tts_rate", 90, 260)
        self._scale(c, "Громкость (%)", "volume", 10, 100, scale=100)

        tk.Frame(c, bg=LINE, height=1).pack(fill="x", pady=10)

        self._check(c, "Спрашивать подтверждение перед выключением ПК", "confirm_dangerous")
        self._check(c, "Включать микрофон сразу при запуске", "listen_on_launch")
        self._check(c, "Приветствие при старте", "play_boot_phrase")

        tk.Frame(c, bg=LINE, height=1).pack(fill="x", pady=10)

        tk.Label(c, text="ОБНОВЛЕНИЯ ЧЕРЕЗ GITHUB", font=mono(9, True), fg=CYAN_DIM,
                 bg=BG, anchor="w").pack(fill="x", pady=(0, 2))
        tk.Label(c, text=f"Текущая версия: {__version__}   ·   {app.updater.describe()}",
                 font=ui_font(8), fg=MUTED, bg=BG, anchor="w").pack(fill="x")
        self._entry(c, "Репозиторий в формате «логин/название»", "update_repo")
        self._check(c, "Проверять обновления при запуске", "update_check_on_start")
        self._check(c, "Устанавливать обновления без вопросов", "update_auto_install")
        self._check(c, "Предлагать бета-версии (pre-release)", "update_prereleases")
        tk.Button(c, text="Проверить обновления сейчас", font=ui_font(9), fg=CYAN, bg=PANEL,
                  bd=0, cursor="hand2", pady=6, activebackground=LINE,
                  command=lambda: (self._save(), app._check_updates(force=True))
                  ).pack(fill="x", pady=(6, 0))

        tk.Button(btns, text="СОХРАНИТЬ", font=ui_font(10, True), fg=BG, bg=CYAN, bd=0,
                  padx=18, pady=8, cursor="hand2", command=self._save).pack(side="right")
        tk.Button(btns, text="Отмена", font=ui_font(10), fg=MUTED, bg=PANEL, bd=0,
                  padx=14, pady=8, cursor="hand2", command=self.destroy).pack(side="right", padx=8)
        tk.Button(btns, text="Открыть config.json", font=ui_font(9), fg=MUTED, bg=BG, bd=0,
                  cursor="hand2", command=self._open_cfg).pack(side="left")

    # ---------- виджеты ----------
    def _label(self, parent, text):
        tk.Label(parent, text=text, font=ui_font(9), fg=MUTED, bg=BG, anchor="w").pack(fill="x", pady=(6, 2))

    def _entry(self, parent, label, key, listmode=False):
        self._label(parent, label)
        val = self.cfg.get(key, "")
        if listmode and isinstance(val, list):
            val = ", ".join(val)
        v = tk.StringVar(value=str(val))
        self.vars[key] = v
        e = tk.Entry(parent, textvariable=v, bg=PANEL2, fg=TEXT, font=mono(10),
                     bd=0, insertbackground=CYAN, relief="flat")
        e.pack(fill="x", ipady=6)
        setattr(v, "_listmode", listmode)

    def _check(self, parent, label, key):
        v = tk.BooleanVar(value=bool(self.cfg.get(key, False)))
        self.vars[key] = v
        tk.Checkbutton(parent, text=label, variable=v, font=ui_font(9), fg=TEXT, bg=BG,
                       selectcolor=PANEL2, activebackground=BG, activeforeground=CYAN,
                       bd=0, highlightthickness=0, anchor="w").pack(fill="x", pady=2)

    def _combo(self, parent, label, key, options, as_int=False):
        self._label(parent, label)
        cur = self.cfg.get(key, "")
        cur_s = "" if cur is None else str(cur)
        labels = [o[0] for o in options]
        default = labels[0]
        for lbl, val in options:
            if val == cur_s:
                default = lbl
                break
        v = tk.StringVar(value=default)
        self.vars[key] = v
        setattr(v, "_options", options)
        setattr(v, "_as_int", as_int)
        cb = ttk.Combobox(parent, textvariable=v, values=labels, state="readonly", font=("", 9))
        cb.pack(fill="x", ipady=3)

    def _scale(self, parent, label, key, lo, hi, scale=1):
        self._label(parent, label)
        cur = self.cfg.get(key, lo)
        v = tk.DoubleVar(value=float(cur) * scale if scale != 1 else float(cur))
        self.vars[key] = v
        setattr(v, "_scale", scale)
        tk.Scale(parent, variable=v, from_=lo, to=hi, orient="horizontal", bg=BG, fg=CYAN,
                 troughcolor=PANEL2, highlightthickness=0, bd=0, sliderrelief="flat",
                 activebackground=CYAN, font=mono(8)).pack(fill="x")

    def _open_cfg(self):
        from .commands import open_path

        config.save(self.cfg)
        open_path(config.CONFIG_PATH)

    def _save(self):
        for key, v in self.vars.items():
            if isinstance(v, tk.BooleanVar):
                self.cfg[key] = bool(v.get())
            elif hasattr(v, "_options"):
                chosen = v.get()
                val = ""
                for lbl, raw in getattr(v, "_options"):
                    if lbl == chosen:
                        val = raw
                        break
                if getattr(v, "_as_int", False):
                    self.cfg[key] = int(val) if val != "" else None
                else:
                    self.cfg[key] = val
            elif hasattr(v, "_scale"):
                sc = getattr(v, "_scale")
                self.cfg[key] = round(float(v.get()) / sc, 3) if sc != 1 else int(float(v.get()))
            elif getattr(v, "_listmode", False):
                self.cfg[key] = [s.strip().lower() for s in str(v.get()).split(",") if s.strip()]
            else:
                self.cfg[key] = v.get()

        config.save(self.cfg)
        self.app.assistant.cfg = self.cfg
        self.app.assistant.voice.cfg = self.cfg
        self.app.assistant.listener.cfg = self.cfg
        self.app._append("system", "Настройки сохранены. Для смены микрофона переключите его кнопкой.")
        self.destroy()


def run():
    app = JarvisApp()
    app.mainloop()
