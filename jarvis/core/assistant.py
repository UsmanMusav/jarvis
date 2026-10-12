"""
Диспетчер Джарвиса: активационное слово, выбор языка, маршрутизация команд,
подтверждения опасных действий, журнал диалога.

Связывает между собой speech (уши), commands (руки), brain (голова) и audio_out (голос).
"""
from __future__ import annotations

import re
import time

from . import brain, commands, config
from .audio_out import Voice
from .commands import Reply, norm
from .speech import Listener
from .version import __version__

STOP_WORDS = re.compile(r"^(?:стоп|хватит|замолчи|тихо|молчи|отмена|stop|quiet|shut up|silence)$")
SLEEP_WORDS = re.compile(r"^(?:спи|отключись|отбой|спасибо это всё|go to sleep|sleep|dismissed|"
                         r"отключайся|выключись|стой режим ожидания)$")
YES_WORDS = re.compile(r"^(?:да|ага|подтверждаю|давай|верно|точно|yes|yeah|confirm|sure|do it|подтвердить)\b")
NO_WORDS = re.compile(r"^(?:нет|не надо|отмена|отмени|стой|no|cancel|nope|никогда)\b")


def detect_lang(text: str, cfg: dict) -> str:
    setting = cfg.get("language", "auto")
    if setting in ("ru", "en"):
        return setting
    cyr = sum(1 for ch in text if "а" <= ch.lower() <= "я" or ch.lower() == "ё")
    lat = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    return "en" if lat > cyr else "ru"


class Assistant:
    """
    on_event(kind, text, extra) — колбэк для интерфейса.
        kind: "user" | "jarvis" | "system" | "error" | "status" | "display"
    """

    def __init__(self, cfg: dict, on_event=None, on_speaking=None, on_listen_state=None):
        self.cfg = cfg
        self.on_event = on_event or (lambda kind, text, extra=None: None)
        self.on_listen_state = on_listen_state or (lambda s: None)

        self.voice = Voice(cfg, on_state=self._voice_state)
        self._on_speaking = on_speaking or (lambda b: None)

        self.listener = Listener(
            cfg,
            on_text=self._on_stt,
            on_status=self._on_stt_status,
        )
        self.timers = brain.Timers(on_fire=self._timer_fired)

        self.pending_confirm: str | None = None
        self.awake_until: float = 0.0
        self.muted = False
        self.history: list[tuple[str, str]] = []
        # интерфейс подставляет сюда проверку обновлений
        self.update_handler = None

    # ------------------------------------------------------------------ состояние
    def _voice_state(self, speaking: bool):
        # пока Джарвис говорит — микрофон заглушен, чтобы он не услышал сам себя
        if speaking:
            self.listener.pause()
        else:
            time.sleep(0.25)
            self.listener.resume()
        self._on_speaking(speaking)

    def _on_stt_status(self, state: str):
        self.on_listen_state(state)

    def _timer_fired(self, label: str):
        msg = f"Сэр, время вышло. Таймер: {label}." if self.cfg.get("language") != "en" \
            else f"Time is up, sir. Timer: {label}."
        self.on_event("jarvis", msg)
        self.voice.say(msg, "done", detect_lang(msg, self.cfg))

    # ------------------------------------------------------------------ вход
    def _on_stt(self, text: str):
        if text.startswith("__error__"):
            self.on_event("error", text[len("__error__"):])
            return
        self.handle_voice(text)

    def handle_voice(self, text: str):
        """Фраза пришла с микрофона — сначала проверяем активационное слово."""
        raw = text.strip()
        if not raw:
            return
        lang = detect_lang(raw, self.cfg)
        t = norm(raw)

        wake = None
        for w in self.cfg.get("wake_words", []):
            w = norm(w)
            if not w:
                continue
            m = re.search(rf"\b{re.escape(w)}\b", t)
            if m:
                wake = m
                break

        need_wake = bool(self.cfg.get("require_wake_word", True))
        awake = time.time() < self.awake_until

        if need_wake and wake is None and not awake and self.pending_confirm is None:
            self.on_event("system", f"(мимо) {raw}")
            return

        command = t
        if wake is not None:
            command = (t[:wake.start()] + " " + t[wake.end():]).strip()
            command = re.sub(r"^(?:пожалуйста|слушай|эй|hey|please)\s+", "", command).strip()
            command = re.sub(r"\s+(?:пожалуйста|please)$", "", command).strip()

        self.on_event("user", raw)

        if not command:
            # позвали по имени, но без команды
            self.awake_until = time.time() + float(self.cfg.get("follow_up_window", 12))
            self.voice.say(clip_key="wake", lang=lang)
            self.on_event("jarvis", self.voice.clip_text("wake", lang) or "Да, сэр?")
            return

        self.awake_until = time.time() + float(self.cfg.get("follow_up_window", 12))
        self._execute(command, raw, lang)

    def handle_text(self, text: str):
        """Команда введена с клавиатуры — активационное слово не требуется."""
        raw = text.strip()
        if not raw:
            return
        lang = detect_lang(raw, self.cfg)
        t = norm(raw)
        for w in self.cfg.get("wake_words", []):
            t = re.sub(rf"\b{re.escape(norm(w))}\b", " ", t).strip()
        t = re.sub(r"\s+", " ", t).strip(" ,")
        self.on_event("user", raw)
        if not t:
            self.voice.say(clip_key="wake", lang=lang)
            self.on_event("jarvis", self.voice.clip_text("wake", lang) or "Да, сэр?")
            return
        self._execute(t, raw, lang)

    # ------------------------------------------------------------------ выполнение
    def _execute(self, command: str, raw: str, lang: str):
        self.history.append(("user", raw))

        # --- прервать речь ---
        if STOP_WORDS.match(command):
            self.voice.shutup()
            self.on_event("system", "Речь прервана.")
            return

        # --- уйти в режим ожидания ---
        if SLEEP_WORDS.match(command):
            self.awake_until = 0
            self.voice.say(clip_key="standby", lang=lang)
            self.on_event("jarvis", self.voice.clip_text("standby", lang) or "Перехожу в режим ожидания, сэр.")
            return

        # --- обновления ---
        if re.search(r"(провер\w*\s+обновлени|есть ли обновлени|обнови себя|обновись|"
                     r"check\s+for\s+updates?|update\s+yourself)", command):
            msg = "Проверяю обновления, сэр." if lang == "ru" else "Checking for updates, sir."
            self.on_event("jarvis", msg)
            self.voice.say(clip_key="busy", lang=lang)
            if self.update_handler:
                self.update_handler()
            else:
                self.on_event("system", "Модуль обновлений доступен только в графическом режиме.")
            return

        if re.search(r"(как(?:ая|ой)\s+(?:у тебя\s+)?верси|твоя версия|номер версии|"
                     r"what\s+version|your\s+version)", command):
            msg = (f"Версия {__version__}, сэр." if lang == "ru"
                   else f"Version {__version__}, sir.")
            self._reply(Reply(msg), lang)
            return

        # --- подтверждение опасного действия ---
        if self.pending_confirm:
            action = self.pending_confirm
            if YES_WORDS.match(command):
                self.pending_confirm = None
                self._reply(commands.confirm_action(action), lang)
                return
            if NO_WORDS.match(command):
                self.pending_confirm = None
                msg = "Отменено, сэр." if lang == "ru" else "Cancelled, sir."
                self._reply(Reply(msg, "done"), lang)
                return
            self.pending_confirm = None  # любая другая фраза = отказ, идём дальше

        # --- действия на компьютере ---
        try:
            rep = commands.handle(command, lang, self.cfg)
        except Exception as e:
            self.on_event("error", f"Ошибка выполнения команды: {e}")
            rep = Reply("Произошла ошибка при выполнении, сэр.", ok=False)

        # --- ответы на вопросы ---
        if rep is None:
            try:
                rep = brain.handle(command, lang, self.cfg, self.timers)
            except Exception as e:
                self.on_event("error", f"Ошибка обработки запроса: {e}")
                rep = None

        # --- не поняли ---
        if rep is None:
            self.voice.say(clip_key="unknown", lang=lang)
            txt = self.voice.clip_text("unknown", lang) or "Не распознал команду, сэр."
            self.on_event("jarvis", txt)
            self.history.append(("jarvis", txt))
            return

        self._reply(rep, lang)

    def _reply(self, rep: Reply, lang: str):
        if rep.confirm:
            self.pending_confirm = rep.confirm
            self.awake_until = time.time() + 25
        if rep.payload.get("display"):
            self.on_event("display", str(rep.payload["display"]))
        if rep.text:
            self.on_event("jarvis" if rep.ok else "error", rep.text)
            self.history.append(("jarvis", rep.text))
        self.voice.say(rep.text, rep.clip_key, lang)

    # ------------------------------------------------------------------ управление
    def start_listening(self) -> bool:
        ok = self.listener.start()
        if not ok:
            self.on_event("error", "Микрофон недоступен: " + (self.listener.why_unusable() or "неизвестная причина"))
        return ok

    def stop_listening(self):
        self.listener.stop()

    def toggle_listening(self) -> bool:
        if self.listener.running:
            self.stop_listening()
            return False
        return self.start_listening()

    def boot(self):
        if self.cfg.get("play_boot_phrase", True):
            lang = "en" if self.cfg.get("language") == "en" else "ru"
            self.voice.say(clip_key="boot", lang=lang)
            self.on_event("jarvis", self.voice.clip_text("boot", lang))

    def shutdown(self):
        try:
            self.stop_listening()
            self.voice.stop()
        except Exception:
            pass
