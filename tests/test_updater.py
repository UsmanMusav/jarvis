"""
Проверка автообновления: сравнение версий и выбор файла под ОС/архитектуру.
Сеть не используется — все данные подставляются вручную.

Запуск:  python tests/test_updater.py
"""
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.updater as up  # noqa: E402
from core.updater import Release, is_newer, parse_version  # noqa: E402

ok = fail = 0


def check(label, got, exp):
    global ok, fail
    if got == exp:
        ok += 1
        print(f"OK   {label}")
    else:
        fail += 1
        print(f"FAIL {label}\n       получили {got!r}, ждали {exp!r}")


print("=== разбор версий ===")
check("1.2.3", parse_version("1.2.3"), (1, 2, 3, ""))
check("v1.2.3", parse_version("v1.2.3"), (1, 2, 3, ""))
check("2.0", parse_version("2.0"), (2, 0, 0, ""))
check("1.2.3-beta1", parse_version("1.2.3-beta1"), (1, 2, 3, "beta1"))

print("\n=== сравнение версий ===")
for remote, local, exp in [
    ("1.1.1", "1.1.0", True),
    ("1.1.0", "1.1.0", False),
    ("1.0.9", "1.1.0", False),
    ("v2.0.0", "1.9.9", True),
    ("1.10.0", "1.9.0", True),          # 10 новее 9, а не «меньше» по строке
    ("1.2.0", "1.2.0-beta1", True),     # релиз новее своей беты
    ("1.2.0-beta2", "1.2.0", False),    # бета не новее релиза
    ("1.2.0-beta2", "1.2.0-beta1", True),
]:
    check(f"{remote} новее {local}", is_newer(remote, local), exp)

print("\n=== выбор файла под систему ===")
OURS = Release(tag="v1.2.0", version="1.2.0", assets=[
    {"name": "JARVIS-Setup-1.2.0.exe", "url": "", "size": 1},
    {"name": "JARVIS-1.2.0-windows-portable.zip", "url": "", "size": 1},
    {"name": "JARVIS-1.2.0-macos.dmg", "url": "", "size": 1},
    {"name": "JARVIS-1.2.0-linux-x86_64.tar.gz", "url": "", "size": 1},
    {"name": "SHA256SUMS.txt", "url": "", "size": 1},
])

# Реальная раскладка из релиза ripgrep: много архитектур, "darwin" содержит "win"
RIPGREP = Release(tag="15.2.0", version="15.2.0", assets=[
    {"name": "ripgrep-15.2.0-x86_64-pc-windows-msvc.zip", "url": "", "size": 1},
    {"name": "ripgrep-15.2.0-aarch64-pc-windows-msvc.zip", "url": "", "size": 1},
    {"name": "ripgrep-15.2.0-x86_64-apple-darwin.tar.gz", "url": "", "size": 1},
    {"name": "ripgrep-15.2.0-aarch64-apple-darwin.tar.gz", "url": "", "size": 1},
    {"name": "ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz", "url": "", "size": 1},
    {"name": "ripgrep-15.2.0-aarch64-unknown-linux-gnu.tar.gz", "url": "", "size": 1},
    {"name": "ripgrep_15.2.0-1_amd64.deb", "url": "", "size": 1},
])

PLATFORMS = {
    "win_x64":   ((True, False, False), "AMD64"),
    "mac_intel": ((False, True, False), "x86_64"),
    "mac_arm":   ((False, True, False), "arm64"),
    "linux_x64": ((False, False, True), "x86_64"),
    "linux_arm": ((False, False, True), "aarch64"),
}

_real_machine = platform.machine


def pick(rel, where):
    flags, mach = PLATFORMS[where]
    up.IS_WIN, up.IS_MAC, up.IS_LINUX = flags
    up.platform.machine = lambda: mach
    a = rel.pick_asset()
    return a["name"] if a else None


try:
    check("наш релиз · Windows", pick(OURS, "win_x64"), "JARVIS-Setup-1.2.0.exe")
    check("наш релиз · macOS", pick(OURS, "mac_intel"), "JARVIS-1.2.0-macos.dmg")
    check("наш релиз · Linux", pick(OURS, "linux_x64"), "JARVIS-1.2.0-linux-x86_64.tar.gz")

    check("ripgrep · Windows x64", pick(RIPGREP, "win_x64"),
          "ripgrep-15.2.0-x86_64-pc-windows-msvc.zip")
    # главная ловушка: в слове "darwin" содержится "win"
    check("ripgrep · macOS Intel (не перепутать с darWINdows)", pick(RIPGREP, "mac_intel"),
          "ripgrep-15.2.0-x86_64-apple-darwin.tar.gz")
    check("ripgrep · macOS ARM", pick(RIPGREP, "mac_arm"),
          "ripgrep-15.2.0-aarch64-apple-darwin.tar.gz")
    check("ripgrep · Linux x64", pick(RIPGREP, "linux_x64"),
          "ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz")
    check("ripgrep · Linux ARM", pick(RIPGREP, "linux_arm"),
          "ripgrep-15.2.0-aarch64-unknown-linux-gnu.tar.gz")

    check("контрольные суммы находятся", OURS.sums_asset()["name"], "SHA256SUMS.txt")
    check("пустой релиз -> None", Release().pick_asset(), None)
    check("только сторонние файлы -> None",
          Release(assets=[{"name": "notes.txt", "url": "", "size": 1}]).pick_asset(), None)
finally:
    up.platform.machine = _real_machine
    up.IS_WIN = platform.system() == "Windows"
    up.IS_MAC = platform.system() == "Darwin"
    up.IS_LINUX = platform.system() == "Linux"

print("\n" + "-" * 60)
print(f"Успешно: {ok}   Провалено: {fail}")
sys.exit(0 if fail == 0 else 1)
