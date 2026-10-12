"""
Настройки J.A.R.V.I.S.
Хранятся в config.json рядом с main.py. Файл создаётся автоматически
при первом запуске и может быть отредактирован руками или из GUI.
"""
from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

# Папка приложения: рядом с .exe у собранной версии, рядом с main.py у исходников
APP_DIR = Path(sys.executable).resolve().parent if FROZEN \
    else Path(__file__).resolve().parent.parent

# Ресурсы: внутри бандла PyInstaller или рядом с исходниками
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)) if FROZEN \
    else Path(__file__).resolve().parent.parent
ASSETS_DIR = BUNDLE_DIR / "assets"


def _user_data_dir() -> Path:
    """Куда писать настройки и заметки.

    У установленной версии папка программы может быть недоступна для записи,
    поэтому пользовательские данные идут в стандартное место ОС.
    """
    if not FROZEN:
        return APP_DIR
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "Jarvis"


DATA_DIR = _user_data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
NOTES_PATH = DATA_DIR / "notes.txt"

DEFAULTS: dict = {
    # ---------- Язык ----------
    # "ru" | "en" | "auto"  (auto = определять по распознанному тексту)
    "language": "auto",

    # ---------- Активационное слово ----------
    "require_wake_word": True,
    "wake_words": [
        "джарвис", "джарвес", "джервис", "жарвис", "дарвис", "чарвис",
        "jarvis", "jervis", "service",
    ],
    # Сколько секунд после срабатывания слушать команды без повторения имени
    "follow_up_window": 12,

    # ---------- Распознавание речи ----------
    "stt_engine": "google",        # "google" (нужен интернет, бесплатно) | "vosk" (оффлайн)
    "vosk_model_path": "",         # путь к распакованной модели vosk
    "mic_index": None,             # None = микрофон по умолчанию
    "energy_threshold": 300,       # порог громкости; больше = менее чувствительно
    "dynamic_energy": True,
    "pause_threshold": 0.8,        # сек. тишины = конец фразы
    "phrase_time_limit": 10,       # максимальная длина фразы, сек.

    # ---------- Синтез речи ----------
    # "clips"   — только заготовленные клипы (молчит, если клипа нет)
    # "auto"    — клипы + локальный синтез для остального  (РЕКОМЕНДУЕТСЯ)
    # "pyttsx3" — только локальный синтез
    # "edge"    — нейросетевой онлайн-голос edge-tts (нужен pip install edge-tts)
    "tts_engine": "auto",
    "tts_rate": 170,               # скорость локального голоса
    "tts_voice_hint": "",          # часть имени системного голоса, напр. "Pavel" / "Irina"
    "edge_voice_ru": "ru-RU-DmitryNeural",
    "edge_voice_en": "en-GB-RyanNeural",
    "volume": 0.9,

    # ---------- Поведение ----------
    "city": "Астрахань",
    "user_title_ru": "сэр",
    "user_title_en": "sir",
    "confirm_dangerous": True,     # спрашивать перед выключением/перезагрузкой
    "listen_on_launch": False,     # сразу включать микрофон при старте
    "play_boot_phrase": True,
    "default_search": "https://www.google.com/search?q={q}",

    # ---------- Обновления через GitHub ----------
    # Укажите свой репозиторий в виде "логин/название". Обновления берутся
    # из GitHub Releases: приложение само скачает файл для вашей ОС.
    "update_repo": "",
    "update_check_on_start": True,     # проверять при запуске
    "update_auto_install": False,      # ставить сразу, без вопроса
    "update_interval_hours": 24,       # не чаще раза в сутки
    "update_prereleases": False,       # предлагать бета-версии
    "update_last_check": 0,            # служебное поле

    # ---------- Свои программы ----------
    # "фотошоп": "C:/Program Files/Adobe/Photoshop/Photoshop.exe"
    "custom_apps": {},
    # "работа": "https://mail.google.com"
    "custom_sites": {},
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
        except Exception as e:  # повреждённый конфиг не должен ронять приложение
            print(f"[config] не удалось прочитать config.json: {e}")
    return cfg


def save(cfg: dict) -> bool:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[config] не удалось сохранить config.json: {e}")
        return False


def ensure_exists() -> dict:
    cfg = load()
    if not CONFIG_PATH.exists():
        save(cfg)
    return cfg
