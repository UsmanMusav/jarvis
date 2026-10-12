# -*- mode: python ; coding: utf-8 -*-
"""
Сборка J.A.R.V.I.S. в исполняемый файл.
Запускать из корня проекта:   pyinstaller build/jarvis.spec --noconfirm
"""
import platform
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent          # noqa: F821  (SPECPATH даёт PyInstaller)
SYSTEM = platform.system()

sys.path.insert(0, str(ROOT))
from core.version import __version__            # noqa: E402

# ---- ресурсы, которые должны попасть внутрь ----
datas = [
    (str(ROOT / "assets" / "voices.json"), "assets"),
    (str(ROOT / "assets" / "voice_ru"), "assets/voice_ru"),
    (str(ROOT / "assets" / "voice_en"), "assets/voice_en"),
    (str(ROOT / "assets" / "icons"), "assets/icons"),
    (str(ROOT / "assets" / "icon.png"), "assets"),
    (str(ROOT / "README.md"), "."),
]

# ---- модули, которые PyInstaller не находит сам ----
hidden = [
    "pyttsx3.drivers",
    "pygame",
    "speech_recognition",
    "psutil",
    "tkinter",
    "tkinter.ttk",
    "tkinter.font",
]
if SYSTEM == "Windows":
    hidden += ["pyttsx3.drivers.sapi5", "comtypes", "win32com", "win32com.client", "pythoncom"]
elif SYSTEM == "Darwin":
    hidden += ["pyttsx3.drivers.nsss"]
else:
    hidden += ["pyttsx3.drivers.espeak"]

excludes = [
    "numpy", "scipy", "pandas", "matplotlib", "PIL", "pytest",
    "IPython", "notebook", "setuptools", "pip",
]

icon_win = str(ROOT / "assets" / "icons" / "jarvis.ico")
icon_mac = str(ROOT / "assets" / "icons" / "jarvis.icns")

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JARVIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                 # без чёрного окна консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_win if SYSTEM == "Windows" else (icon_mac if SYSTEM == "Darwin" else None),
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="JARVIS",
)

if SYSTEM == "Darwin":
    app = BUNDLE(
        coll,
        name="JARVIS.app",
        icon=icon_mac,
        bundle_identifier="com.jarvisproject.assistant",
        version=__version__,
        info_plist={
            "CFBundleName": "JARVIS",
            "CFBundleDisplayName": "J.A.R.V.I.S.",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            # macOS обязательно требует объяснить, зачем приложению микрофон
            "NSMicrophoneUsageDescription":
                "J.A.R.V.I.S. использует микрофон для распознавания голосовых команд.",
            "NSAppleEventsUsageDescription":
                "J.A.R.V.I.S. управляет громкостью, снимками экрана и другими функциями системы.",
        },
    )
