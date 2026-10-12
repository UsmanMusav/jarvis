"""
Голос Джарвиса.

Логика:
  1. Если у фразы есть ключ (clip_key) и для него записан wav —
     проигрываем студийный клип голосом Джарвиса.
  2. Иначе говорим текст локальным синтезом (pyttsx3 / системная утилита).
  3. Опционально — нейросетевым голосом edge-tts, если он включён в настройках.

Всё воспроизведение идёт в отдельном потоке-очереди, чтобы интерфейс не замирал.
"""
from __future__ import annotations

import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import config

SYSTEM = platform.system()  # Windows / Darwin / Linux

# ---------------------------------------------------------------- проигрыватель


class _Player:
    """Воспроизведение wav/mp3 файлов. pygame -> системные утилиты -> winsound."""

    def __init__(self):
        self._pygame_ok = False
        try:
            import pygame  # noqa

            pygame.mixer.init()
            self._pygame = pygame
            self._pygame_ok = True
        except Exception:
            self._pygame = None

    @property
    def backend(self) -> str:
        if self._pygame_ok:
            return "pygame"
        if SYSTEM == "Windows":
            return "winsound"
        if SYSTEM == "Darwin":
            return "afplay"
        for p in ("paplay", "aplay", "ffplay", "mpv"):
            if shutil.which(p):
                return p
        return "нет"

    def play(self, path: str, volume: float = 0.9, block: bool = True) -> bool:
        path = str(path)
        if not os.path.exists(path):
            return False

        if self._pygame_ok:
            try:
                snd = self._pygame.mixer.Sound(path)
                snd.set_volume(max(0.0, min(1.0, volume)))
                ch = snd.play()
                if block and ch is not None:
                    while ch.get_busy():
                        time.sleep(0.05)
                return True
            except Exception:
                pass  # падаем на системный проигрыватель

        try:
            if SYSTEM == "Windows":
                import winsound

                flags = winsound.SND_FILENAME
                if not block:
                    flags |= winsound.SND_ASYNC
                winsound.PlaySound(path, flags)
                return True
            if SYSTEM == "Darwin":
                cmd = ["afplay", path]
            else:
                for p, args in (
                    ("paplay", [path]),
                    ("aplay", ["-q", path]),
                    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet", path]),
                    ("mpv", ["--really-quiet", path]),
                ):
                    if shutil.which(p):
                        cmd = [p] + args
                        break
                else:
                    return False
            if block:
                subprocess.run(cmd, check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    def stop(self):
        if self._pygame_ok:
            try:
                self._pygame.mixer.stop()
            except Exception:
                pass


# ---------------------------------------------------------------- локальный TTS


class _LocalTTS:
    """pyttsx3, а если его нет — системная утилита (say / espeak / SAPI)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.available = False
        self.engine_name = "нет"
        try:
            import pyttsx3  # noqa

            self._pyttsx3 = pyttsx3
            self.available = True
            self.engine_name = "pyttsx3"
        except Exception:
            self._pyttsx3 = None
            if SYSTEM == "Darwin" and shutil.which("say"):
                self.available, self.engine_name = True, "say"
            elif shutil.which("espeak-ng") or shutil.which("espeak"):
                self.available, self.engine_name = True, "espeak"
            elif SYSTEM == "Windows":
                self.available, self.engine_name = True, "SAPI"

    def _pick_voice(self, engine, lang: str):
        hint = (self.cfg.get("tts_voice_hint") or "").lower().strip()
        try:
            voices = engine.getProperty("voices")
        except Exception:
            return
        chosen = None
        if hint:
            for v in voices:
                if hint in (v.name or "").lower() or hint in (v.id or "").lower():
                    chosen = v
                    break
        if chosen is None:
            # мужской голос нужного языка, если получится
            want = "russian" if lang == "ru" else "english"
            male = ("pavel", "dmitry", "yuri", "male", "david", "george", "daniel", "ryan")
            cands = []
            for v in voices:
                blob = f"{v.name} {v.id} {getattr(v, 'languages', '')}".lower()
                score = 0
                if want in blob or (lang == "ru" and "ru" in blob) or (lang == "en" and "en-" in blob):
                    score += 2
                if any(m in blob for m in male):
                    score += 1
                if score:
                    cands.append((score, v))
            if cands:
                cands.sort(key=lambda x: -x[0])
                chosen = cands[0][1]
        if chosen is not None:
            try:
                engine.setProperty("voice", chosen.id)
            except Exception:
                pass

    def say(self, text: str, lang: str = "ru") -> bool:
        if not text.strip():
            return True
        if self._pyttsx3 is not None:
            try:
                # Движок создаётся заново на каждую фразу — так он стабильнее в потоках
                engine = self._pyttsx3.init()
                engine.setProperty("rate", int(self.cfg.get("tts_rate", 170)))
                engine.setProperty("volume", float(self.cfg.get("volume", 0.9)))
                self._pick_voice(engine, lang)
                engine.say(text)
                engine.runAndWait()
                try:
                    engine.stop()
                except Exception:
                    pass
                return True
            except Exception as e:
                print(f"[tts] pyttsx3: {e}")

        try:
            if self.engine_name == "say":
                subprocess.run(["say", text], check=False)
                return True
            if self.engine_name == "espeak":
                exe = shutil.which("espeak-ng") or shutil.which("espeak")
                subprocess.run([exe, "-v", "ru" if lang == "ru" else "en", "-s", "160", text],
                               check=False, stderr=subprocess.DEVNULL)
                return True
            if self.engine_name == "SAPI":
                safe = text.replace("'", "''")
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Add-Type -AssemblyName System.Speech; "
                     f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe}')"],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
        except Exception as e:
            print(f"[tts] {self.engine_name}: {e}")
        return False


# ---------------------------------------------------------------- edge-tts


class _EdgeTTS:
    def __init__(self, cfg: dict, player: _Player):
        self.cfg, self.player = cfg, player
        try:
            import edge_tts  # noqa

            self._mod = edge_tts
            self.available = True
        except Exception:
            self._mod = None
            self.available = False

    def say(self, text: str, lang: str = "ru") -> bool:
        if not self.available:
            return False
        import asyncio

        voice = self.cfg.get("edge_voice_ru" if lang == "ru" else "edge_voice_en")
        tmp = Path(tempfile.gettempdir()) / f"jarvis_edge_{int(time.time()*1000)}.mp3"
        try:
            async def _run():
                com = self._mod.Communicate(text, voice)
                await com.save(str(tmp))

            asyncio.run(_run())
            ok = self.player.play(tmp, float(self.cfg.get("volume", 0.9)), block=True)
            return ok
        except Exception as e:
            print(f"[tts] edge-tts: {e}")
            return False
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass


# ---------------------------------------------------------------- фасад


class Voice:
    """Единая точка: voice.say('текст', clip_key='done')."""

    def __init__(self, cfg: dict, on_state=None):
        self.cfg = cfg
        self.on_state = on_state or (lambda speaking: None)
        self.player = _Player()
        self.local = _LocalTTS(cfg)
        self.edge = _EdgeTTS(cfg, self.player)
        self.clips = self._load_clip_map()
        self.muted = False

        self._q: "queue.Queue" = queue.Queue()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._loop, daemon=True, name="jarvis-tts")
        self._worker.start()

    # ---------- клипы ----------
    def _load_clip_map(self) -> dict:
        path = config.ASSETS_DIR / "voices.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {k: v for k, v in data.items() if not k.startswith("_")}
        except Exception:
            return {}

    def clip_path(self, key: str, lang: str):
        for ext in (".wav", ".mp3", ".ogg"):
            p = config.ASSETS_DIR / f"voice_{lang}" / f"{key}{ext}"
            if p.exists():
                return p
        return None

    def clip_text(self, key: str, lang: str) -> str:
        return (self.clips.get(lang, {}) or {}).get(key, "")

    def has_clip(self, key: str, lang: str) -> bool:
        return self.clip_path(key, lang) is not None

    # ---------- публичное API ----------
    def say(self, text: str = "", clip_key: str | None = None, lang: str = "ru", wait: bool = False):
        """Поставить фразу в очередь. wait=True — дождаться окончания."""
        if self.muted:
            return
        done = threading.Event() if wait else None
        self._q.put((text or "", clip_key, lang, done))
        if done is not None:
            done.wait(timeout=30)

    def say_now(self, text: str = "", clip_key: str | None = None, lang: str = "ru"):
        """Очистить очередь и сказать немедленно."""
        self.shutup()
        self.say(text, clip_key, lang)

    def shutup(self):
        try:
            while True:
                _t, _k, _l, ev = self._q.get_nowait()
                if ev:
                    ev.set()
        except queue.Empty:
            pass
        self.player.stop()

    def stop(self):
        self._stop.set()
        self.shutup()
        self._q.put((None, None, None, None))

    # ---------- рабочий поток ----------
    def _loop(self):
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.3)
            except queue.Empty:
                continue
            text, clip_key, lang, done = item
            if text is None:
                break
            try:
                self.on_state(True)
                self._speak(text, clip_key, lang)
            except Exception as e:
                print(f"[tts] ошибка озвучки: {e}")
            finally:
                self.on_state(False)
                if done:
                    done.set()

    def _speak(self, text: str, clip_key: str | None, lang: str):
        mode = self.cfg.get("tts_engine", "auto")
        lang = "en" if lang == "en" else "ru"

        # 1. студийный клип
        if clip_key and mode in ("auto", "clips"):
            p = self.clip_path(clip_key, lang)
            if p is not None:
                if self.player.play(p, float(self.cfg.get("volume", 0.9)), block=True):
                    return
            if mode == "clips":
                # клипа нет — пробуем текст из манифеста локальным голосом
                text = text or self.clip_text(clip_key, lang)

        if not text and clip_key:
            text = self.clip_text(clip_key, lang)
        if not text:
            return

        # 2. edge-tts
        if mode == "edge" and self.edge.available:
            if self.edge.say(text, lang):
                return

        # 3. локальный синтез
        if self.local.available:
            self.local.say(text, lang)

    # ---------- диагностика ----------
    def status(self) -> dict:
        ru = sum(1 for k in self.clips.get("ru", {}) if self.has_clip(k, "ru"))
        en = sum(1 for k in self.clips.get("en", {}) if self.has_clip(k, "en"))
        return {
            "player": self.player.backend,
            "local_tts": self.local.engine_name if self.local.available else "нет",
            "edge_tts": "да" if self.edge.available else "нет",
            "clips_ru": ru,
            "clips_en": en,
        }
