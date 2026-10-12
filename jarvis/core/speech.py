"""
Распознавание речи (STT).

Два движка:
  * "google" — бесплатный Web Speech API через библиотеку SpeechRecognition.
               Ключ не нужен, но нужен интернет. Отлично понимает русский.
  * "vosk"   — полностью оффлайн. Нужно скачать модель и указать путь в настройках.

Класс Listener работает в фоновом потоке и дёргает колбэки:
    on_text(text)      — распознанная фраза
    on_status(state)   — "idle" | "listening" | "recognizing" | "error"
    on_level(0..1)     — уровень громкости для анимации (не всегда доступен)
"""
from __future__ import annotations

import json
import threading
import time

AVAILABLE = {"sr": False, "mic": False, "vosk": False, "sd": False}

try:
    import speech_recognition as sr  # noqa

    AVAILABLE["sr"] = True
except Exception:
    sr = None

if AVAILABLE["sr"]:
    try:
        import pyaudio  # noqa

        AVAILABLE["mic"] = True
    except Exception:
        AVAILABLE["mic"] = False

try:
    import vosk  # noqa

    AVAILABLE["vosk"] = True
except Exception:
    vosk = None

try:
    import sounddevice  # noqa

    AVAILABLE["sd"] = True
except Exception:
    sounddevice = None


def list_microphones() -> list[str]:
    if not (AVAILABLE["sr"] and AVAILABLE["mic"]):
        return []
    try:
        return list(sr.Microphone.list_microphone_names())
    except Exception:
        return []


def diagnostics() -> dict:
    return {
        "SpeechRecognition": "да" if AVAILABLE["sr"] else "нет",
        "микрофон (PyAudio)": "да" if AVAILABLE["mic"] else "нет",
        "vosk (оффлайн)": "да" if AVAILABLE["vosk"] else "нет",
        "микрофонов найдено": len(list_microphones()),
    }


class Listener:
    def __init__(self, cfg: dict, on_text=None, on_status=None, on_level=None):
        self.cfg = cfg
        self.on_text = on_text or (lambda t: None)
        self.on_status = on_status or (lambda s: None)
        self.on_level = on_level or (lambda v: None)

        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._paused = threading.Event()   # выставлен = микрофон временно заглушен
        self._recognizer = None
        self._vosk_model = None

    # ------------------------------------------------------------------ состояние
    @property
    def running(self) -> bool:
        return self._running.is_set()

    @property
    def usable(self) -> bool:
        if self.cfg.get("stt_engine") == "vosk":
            return AVAILABLE["vosk"] and AVAILABLE["sd"] and bool(self.cfg.get("vosk_model_path"))
        return AVAILABLE["sr"] and AVAILABLE["mic"]

    def why_unusable(self) -> str:
        if self.cfg.get("stt_engine") == "vosk":
            if not AVAILABLE["vosk"]:
                return "не установлен пакет vosk  (pip install vosk)"
            if not AVAILABLE["sd"]:
                return "не установлен пакет sounddevice  (pip install sounddevice)"
            if not self.cfg.get("vosk_model_path"):
                return "не указан путь к модели vosk в настройках"
            return ""
        if not AVAILABLE["sr"]:
            return "не установлен SpeechRecognition  (pip install SpeechRecognition)"
        if not AVAILABLE["mic"]:
            return "не установлен PyAudio — нет доступа к микрофону  (pip install PyAudio)"
        if not list_microphones():
            return "микрофон не найден в системе"
        return ""

    # ------------------------------------------------------------------ управление
    def start(self) -> bool:
        if self.running:
            return True
        if not self.usable:
            self.on_status("error")
            return False
        self._running.set()
        self._paused.clear()
        target = self._loop_vosk if self.cfg.get("stt_engine") == "vosk" else self._loop_google
        self._thread = threading.Thread(target=target, daemon=True, name="jarvis-stt")
        self._thread.start()
        return True

    def stop(self):
        self._running.clear()
        self.on_status("idle")

    def pause(self):
        """Заглушить микрофон, пока Джарвис говорит (чтобы не слышать сам себя)."""
        self._paused.set()

    def resume(self):
        self._paused.clear()

    # ------------------------------------------------------------------ google
    def _make_recognizer(self):
        r = sr.Recognizer()
        r.energy_threshold = int(self.cfg.get("energy_threshold", 300))
        r.dynamic_energy_threshold = bool(self.cfg.get("dynamic_energy", True))
        r.pause_threshold = float(self.cfg.get("pause_threshold", 0.8))
        r.non_speaking_duration = min(0.4, float(self.cfg.get("pause_threshold", 0.8)) / 2)
        return r

    def _lang_codes(self) -> list[str]:
        lang = self.cfg.get("language", "auto")
        if lang == "ru":
            return ["ru-RU"]
        if lang == "en":
            return ["en-US"]
        return ["ru-RU", "en-US"]

    def _loop_google(self):
        r = self._make_recognizer()
        idx = self.cfg.get("mic_index")
        try:
            mic = sr.Microphone(device_index=idx) if idx is not None else sr.Microphone()
        except Exception as e:
            self.on_status("error")
            self.on_text(f"__error__Не удалось открыть микрофон: {e}")
            self._running.clear()
            return

        try:
            with mic as source:
                self.on_status("calibrating")
                try:
                    r.adjust_for_ambient_noise(source, duration=0.8)
                except Exception:
                    pass
        except Exception:
            pass

        while self._running.is_set():
            if self._paused.is_set():
                time.sleep(0.15)
                continue
            try:
                with mic as source:
                    self.on_status("listening")
                    audio = r.listen(
                        source,
                        timeout=4,
                        phrase_time_limit=int(self.cfg.get("phrase_time_limit", 10)),
                    )
            except sr.WaitTimeoutError:
                continue
            except Exception as e:
                self.on_status("error")
                self.on_text(f"__error__Микрофон: {e}")
                time.sleep(1.0)
                continue

            if self._paused.is_set() or not self._running.is_set():
                continue

            self.on_status("recognizing")
            text = ""
            for code in self._lang_codes():
                try:
                    text = r.recognize_google(audio, language=code)
                    if text:
                        break
                except sr.UnknownValueError:
                    continue
                except sr.RequestError as e:
                    self.on_text(f"__error__Нет связи с сервисом распознавания: {e}")
                    time.sleep(1.5)
                    break
                except Exception:
                    continue
            if text:
                self.on_text(text)
        self.on_status("idle")

    # ------------------------------------------------------------------ vosk
    def _loop_vosk(self):
        import queue as _queue

        model_path = self.cfg.get("vosk_model_path")
        try:
            vosk.SetLogLevel(-1)
            if self._vosk_model is None:
                self._vosk_model = vosk.Model(model_path)
        except Exception as e:
            self.on_status("error")
            self.on_text(f"__error__Модель vosk не загрузилась: {e}")
            self._running.clear()
            return

        samplerate = 16000
        rec = vosk.KaldiRecognizer(self._vosk_model, samplerate)
        q: "_queue.Queue" = _queue.Queue()

        def cb(indata, frames, t, status):
            q.put(bytes(indata))

        try:
            with sounddevice.RawInputStream(
                samplerate=samplerate, blocksize=8000, dtype="int16",
                channels=1, callback=cb,
                device=self.cfg.get("mic_index"),
            ):
                self.on_status("listening")
                while self._running.is_set():
                    try:
                        data = q.get(timeout=0.3)
                    except _queue.Empty:
                        continue
                    if self._paused.is_set():
                        continue
                    if rec.AcceptWaveform(data):
                        res = json.loads(rec.Result() or "{}")
                        text = (res.get("text") or "").strip()
                        if text:
                            self.on_status("recognizing")
                            self.on_text(text)
                            self.on_status("listening")
        except Exception as e:
            self.on_status("error")
            self.on_text(f"__error__Аудиопоток vosk: {e}")
        self.on_status("idle")

    # ------------------------------------------------------------------ разовая запись
    def listen_once(self, timeout: float = 6.0) -> str:
        """Записать одну фразу синхронно (кнопка «Сказать один раз»)."""
        if not (AVAILABLE["sr"] and AVAILABLE["mic"]):
            return ""
        r = self._make_recognizer()
        idx = self.cfg.get("mic_index")
        try:
            mic = sr.Microphone(device_index=idx) if idx is not None else sr.Microphone()
            with mic as source:
                self.on_status("listening")
                r.adjust_for_ambient_noise(source, duration=0.4)
                audio = r.listen(source, timeout=timeout,
                                 phrase_time_limit=int(self.cfg.get("phrase_time_limit", 10)))
            self.on_status("recognizing")
            for code in self._lang_codes():
                try:
                    txt = r.recognize_google(audio, language=code)
                    if txt:
                        return txt
                except Exception:
                    continue
        except Exception as e:
            self.on_text(f"__error__{e}")
        finally:
            self.on_status("idle")
        return ""
