"""
Автообновление через GitHub Releases.

Как это работает:
  1. Раз в сутки (или по кнопке) запрашиваем
     https://api.github.com/repos/<owner>/<repo>/releases/latest
  2. Сравниваем версию из тега (v1.2.3) с текущей.
  3. Качаем подходящий файл для текущей ОС, проверяем SHA256 (если в релизе
     есть SHA256SUMS.txt).
  4. Устанавливаем:
       • Windows, установленная версия  -> запускаем Setup.exe в тихом режиме
       • портативная версия (zip/tar)   -> распаковываем и подменяем файлы
       • запуск из исходников с git     -> git pull --ff-only
       • macOS                          -> открываем .dmg

Ключ GitHub не нужен: публичный API, 60 запросов в час.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .version import __version__

API = "https://api.github.com/repos/{repo}/releases/latest"
SYSTEM = platform.system()
IS_WIN, IS_MAC, IS_LINUX = SYSTEM == "Windows", SYSTEM == "Darwin", SYSTEM == "Linux"


# ------------------------------------------------------------------ версии


def parse_version(s: str) -> tuple:
    """'v1.12.3-beta2' -> (1, 12, 3, 'beta2'). Пригодно для сравнения."""
    s = (s or "").strip().lstrip("vV")
    m = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+.]?(.*))?$", s)
    if not m:
        return (0, 0, 0, "")
    major, minor, patch, extra = m.groups()
    # релиз (пустой суффикс) считается новее пред-релиза с тем же номером
    return (int(major), int(minor or 0), int(patch or 0), "" if not extra else extra)


def is_newer(remote: str, local: str) -> bool:
    r, l = parse_version(remote), parse_version(local)
    if r[:3] != l[:3]:
        return r[:3] > l[:3]
    if r[3] == l[3]:
        return False
    if r[3] == "":      # 1.2.0 новее 1.2.0-beta1
        return True
    if l[3] == "":
        return False
    return r[3] > l[3]


# ------------------------------------------------------------------ данные


@dataclass
class Release:
    tag: str = ""
    version: str = ""
    name: str = ""
    notes: str = ""
    url: str = ""
    published: str = ""
    assets: list = field(default_factory=list)   # [{name, url, size}]

    def pick_asset(self) -> dict | None:
        """Выбирает файл под текущую ОС и архитектуру.

        Работает по баллам, а не по первому совпадению: иначе на macOS легко
        скачать windows-архив просто потому, что он тоже .zip.
        """
        machine = platform.machine().lower()
        is_arm = any(k in machine for k in ("arm", "aarch"))

        if IS_WIN:
            strong, okay = (".exe",), (".msi", ".zip")
            mine = {"win", "win32", "win64", "windows", "msvc", "msi"}
            alien = {"mac", "macos", "darwin", "osx", "apple", "linux",
                     "ubuntu", "debian", "fedora", "musl"}
            alien_ext = (".dmg", ".pkg", ".deb", ".rpm", ".appimage")
        elif IS_MAC:
            strong, okay = (".dmg",), (".pkg", ".zip", ".tar.gz")
            mine = {"mac", "macos", "darwin", "osx", "apple", "universal"}
            alien = {"win", "win32", "win64", "windows", "msvc", "linux",
                     "ubuntu", "debian", "fedora", "musl", "gnu"}
            alien_ext = (".exe", ".msi", ".deb", ".rpm", ".appimage")
        else:
            strong, okay = (".appimage",), (".tar.gz", ".tar.xz", ".zip", ".deb", ".rpm")
            mine = {"linux", "ubuntu", "debian", "gnu", "musl", "appimage"}
            alien = {"win", "win32", "win64", "windows", "msvc",
                     "mac", "macos", "darwin", "osx", "apple"}
            alien_ext = (".exe", ".msi", ".dmg", ".pkg")

        arch_mine = {"arm64", "aarch64", "arm"} if is_arm else \
                    {"x86_64", "amd64", "x64", "win64", "intel", "64bit"}
        arch_alien = {"x86_64", "amd64", "x64", "i686", "i386", "x86"} if is_arm else \
                     {"arm64", "aarch64", "armv7", "armhf", "arm", "i686", "i386"}

        skip_ext = (".txt", ".sig", ".asc", ".sha256", ".sha256sum", ".json",
                    ".yml", ".yaml", ".sbom", ".pem", ".md", ".blockmap")

        best, best_score = None, -10 ** 6
        for a in self.assets:
            n = a["name"].lower()
            if n.startswith("sha256") or n.endswith(skip_ext):
                continue
            # Разбор на целые слова: иначе "win" находится внутри "darwin",
            # а "arm" — внутри "firmware".
            toks = set(re.split(r"[^a-z0-9_]+", n))

            score = 0
            if toks & alien or n.endswith(alien_ext):
                score -= 100
            if toks & mine:
                score += 12
            if n.endswith(strong):
                score += 20
            elif n.endswith(okay):
                score += 8
            else:
                score -= 15
            if toks & arch_mine:
                score += 8
            elif toks & arch_alien:
                score -= 10
            if {"setup", "installer"} & toks or "setup" in n:
                score += 6
            if {"debug", "symbols", "source", "sources", "src", "sdk"} & toks:
                score -= 40
            if score > best_score:
                best, best_score = a, score
        return best if best_score > -30 else None

    def sums_asset(self) -> dict | None:
        for a in self.assets:
            if a["name"].lower().startswith("sha256"):
                return a
        return None


# ------------------------------------------------------------------ сеть


def _open(url: str, timeout: float = 20.0):
    req = urllib.request.Request(url, headers={
        "User-Agent": f"JarvisAssistant/{__version__}",
        "Accept": "application/vnd.github+json",
    })
    ctx = ssl.create_default_context()
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


# ------------------------------------------------------------------ установщик


class Updater:
    def __init__(self, cfg: dict, on_event=None):
        self.cfg = cfg
        self.on_event = on_event or (lambda kind, text: None)
        self.latest: Release | None = None
        self.busy = False

    # ---------- где мы живём ----------
    @property
    def app_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return config.APP_DIR

    def install_kind(self) -> str:
        """installer | portable | git | source"""
        if (config.APP_DIR / ".git").exists() and shutil.which("git"):
            return "git"
        if getattr(sys, "frozen", False):
            if IS_WIN and (self.app_dir / "unins000.exe").exists():
                return "installer"
            return "portable"
        return "source"

    def describe(self) -> str:
        return {
            "installer": "установленная версия (обновится через установщик)",
            "portable":  "портативная версия (файлы заменятся на месте)",
            "git":       "запуск из git-репозитория (git pull)",
            "source":    "запуск из исходников",
        }[self.install_kind()]

    # ---------- проверка ----------
    def repo(self) -> str:
        return (self.cfg.get("update_repo") or "").strip().strip("/")

    def check(self, force: bool = False) -> Release | None:
        repo = self.repo()
        if not repo or "/" not in repo:
            self.on_event("error", "Не указан GitHub-репозиторий для обновлений "
                                   "(настройки → «Репозиторий обновлений»).")
            return None
        if not force:
            last = float(self.cfg.get("update_last_check") or 0)
            interval = float(self.cfg.get("update_interval_hours", 24)) * 3600
            if time.time() - last < interval:
                return None
        try:
            with _open(API.format(repo=repo)) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.on_event("error", f"Релизы в {repo} не найдены (или репозиторий приватный).")
            else:
                self.on_event("error", f"GitHub ответил {e.code}.")
            return None
        except Exception as e:
            self.on_event("error", f"Не удалось проверить обновления: {e}")
            return None

        self.cfg["update_last_check"] = time.time()
        config.save(self.cfg)

        rel = Release(
            tag=data.get("tag_name", ""),
            version=(data.get("tag_name") or "").lstrip("vV"),
            name=data.get("name") or data.get("tag_name") or "",
            notes=(data.get("body") or "").strip(),
            url=data.get("html_url", ""),
            published=(data.get("published_at") or "")[:10],
            assets=[{"name": a["name"], "url": a["browser_download_url"], "size": a.get("size", 0)}
                    for a in data.get("assets", [])],
        )
        if data.get("prerelease") and not self.cfg.get("update_prereleases", False):
            return None
        if not is_newer(rel.version, __version__):
            self.on_event("system", f"У вас последняя версия ({__version__}).")
            return None
        self.latest = rel
        return rel

    def check_async(self, callback, force: bool = False):
        def run():
            rel = self.check(force=force)
            try:
                callback(rel)
            except Exception as e:
                print(f"[updater] {e}")

        threading.Thread(target=run, daemon=True).start()

    # ---------- загрузка ----------
    def download(self, rel: Release, progress=None) -> Path | None:
        asset = rel.pick_asset()
        if asset is None:
            self.on_event("error", f"В релизе {rel.tag} нет файла для {SYSTEM}.")
            return None
        dest = Path(tempfile.gettempdir()) / "jarvis_update" / asset["name"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        total = asset.get("size") or 0
        got = 0
        try:
            with _open(asset["url"], timeout=60) as r, open(dest, "wb") as f:
                while True:
                    chunk = r.read(131072)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if progress and total:
                        progress(got / total)
        except Exception as e:
            self.on_event("error", f"Ошибка загрузки: {e}")
            return None

        if not self._verify(dest, rel, asset["name"]):
            return None
        return dest

    def _verify(self, path: Path, rel: Release, name: str) -> bool:
        sums = rel.sums_asset()
        if not sums:
            return True  # контрольных сумм нет — пропускаем
        try:
            with _open(sums["url"]) as r:
                text = r.read().decode("utf-8", "replace")
        except Exception:
            return True
        want = None
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[-1].lstrip("*").lower() == name.lower():
                want = parts[0].lower()
                break
        if not want:
            return True
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest().lower() != want:
            self.on_event("error", "Контрольная сумма не совпала — файл повреждён. Установка отменена.")
            try:
                path.unlink()
            except Exception:
                pass
            return False
        return True

    # ---------- установка ----------
    def apply(self, path: Path) -> bool:
        kind = self.install_kind()
        try:
            if kind == "git":
                return self._apply_git()
            if path.suffix.lower() == ".exe":
                subprocess.Popen([str(path), "/SILENT", "/CLOSEAPPLICATIONS",
                                  "/RESTARTAPPLICATIONS", "/NORESTART"])
                return True
            if path.suffix.lower() == ".dmg":
                subprocess.Popen(["open", str(path)])
                return True
            if path.suffix.lower() == ".appimage":
                target = self.app_dir / path.name
                shutil.copy2(path, target)
                os.chmod(target, 0o755)
                self.on_event("system", f"Новая версия сохранена: {target}")
                return True
            return self._apply_archive(path)
        except Exception as e:
            self.on_event("error", f"Не удалось установить обновление: {e}")
            return False

    def _apply_git(self) -> bool:
        out = subprocess.run(["git", "pull", "--ff-only"], cwd=str(config.APP_DIR),
                             capture_output=True, text=True, timeout=120)
        if out.returncode == 0:
            self.on_event("system", "Обновлено через git. Перезапустите приложение.")
            return True
        self.on_event("error", f"git pull не удался: {out.stderr.strip()[:200]}")
        return False

    def _apply_archive(self, path: Path) -> bool:
        """Распаковать во временную папку и подменить файлы после выхода приложения."""
        tmp = Path(tempfile.mkdtemp(prefix="jarvis_new_"))
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as z:
                z.extractall(tmp)
        elif ".tar" in path.suffixes or path.name.endswith(".tar.gz"):
            with tarfile.open(path) as t:
                t.extractall(tmp)
        else:
            self.on_event("error", f"Неизвестный формат обновления: {path.name}")
            return False

        # если внутри архива одна корневая папка — берём её содержимое
        items = [p for p in tmp.iterdir() if not p.name.startswith(".")]
        src = items[0] if len(items) == 1 and items[0].is_dir() else tmp

        target = self.app_dir
        pid = os.getpid()
        relaunch = sys.executable if getattr(sys, "frozen", False) else None

        if IS_WIN:
            script = tmp.parent / f"jarvis_swap_{pid}.bat"
            exe = f'start "" "{relaunch}"' if relaunch else \
                  f'start "" "{sys.executable}" "{config.APP_DIR / "main.py"}"'
            script.write_text(
                "@echo off\r\n"
                "chcp 65001 >nul\r\n"
                f":wait\r\n"
                f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul\r\n'
                "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait)\r\n"
                f'robocopy "{src}" "{target}" /E /IS /NFL /NDL /NJH /NJS /NP >nul\r\n'
                f"{exe}\r\n"
                f'del "%~f0"\r\n',
                encoding="utf-8")
            subprocess.Popen(["cmd", "/c", str(script)],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            script = tmp.parent / f"jarvis_swap_{pid}.sh"
            exe = f'"{relaunch}"' if relaunch else f'"{sys.executable}" "{config.APP_DIR / "main.py"}"'
            script.write_text(
                "#!/bin/sh\n"
                f"while kill -0 {pid} 2>/dev/null; do sleep 1; done\n"
                f'cp -R "{src}/." "{target}/"\n'
                f"{exe} &\n"
                f'rm -- "$0"\n')
            os.chmod(script, 0o755)
            subprocess.Popen([str(script)], start_new_session=True)

        self.on_event("system", "Обновление распаковано. Приложение перезапустится.")
        return True

    # ---------- всё сразу ----------
    def update_now(self, rel: Release, progress=None, done=None):
        """Скачать и установить в фоне. done(ok: bool) вызывается по окончании."""
        def run():
            self.busy = True
            try:
                p = self.download(rel, progress)
                ok = bool(p) and self.apply(p)
            except Exception as e:
                self.on_event("error", str(e))
                ok = False
            finally:
                self.busy = False
            if done:
                done(ok)

        threading.Thread(target=run, daemon=True).start()
