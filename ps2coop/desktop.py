"""Atalho na área de trabalho e no menu de aplicativos."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .config import (
    APP_ID,
    APP_NAME,
    IS_WINDOWS,
    app_root,
    profile_root,
    resource_root,
    user_data_root,
)
from .games import slugify

INVALID_WINDOWS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
INVALID_DESKTOP = re.compile(r"[\r\n\x00]")
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6",
    "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6",
    "LPT7", "LPT8", "LPT9",
}
_DESKTOP_CACHE: tuple[float, list[Path]] | None = None
_ICON_CACHE: dict[str, Path] = {}


def safe_title(value: str, fallback: str = "PS2 Game") -> str:
    title = INVALID_DESKTOP.sub(" ", value or "").strip()
    if IS_WINDOWS:
        title = INVALID_WINDOWS.sub(" ", title)
        title = title.rstrip(" .")
    title = re.sub(r"\s+", " ", title).strip()
    title = title[:80] or fallback
    if IS_WINDOWS and title.split(".", 1)[0].upper() in WINDOWS_RESERVED:
        title = "_" + title
    return title


def _permanent_icon(name: str) -> Path:
    """Copia o ícone para um lugar que sobrevive ao _MEIPASS do PyInstaller."""
    source = resource_root() / "assets" / name
    if not source.is_file():
        return Path()
    cached = _ICON_CACHE.get(name)
    if cached and cached.is_file():
        return cached
    target_dir = user_data_root() / "icons"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{APP_ID}-{name}"
        if not target.is_file() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)
        _ICON_CACHE[name] = target
        return target
    except OSError:
        return source


def _icon(extensions: tuple[str, ...] | None = None) -> Path:
    exts = extensions or (("icon.ico", "icon.png", "icon.svg") if IS_WINDOWS else ("icon.png", "icon.svg"))
    for name in exts:
        candidate = _permanent_icon(name)
        if candidate.is_file():
            return candidate
    return Path()


def _desktop_dirs() -> list[Path]:
    global _DESKTOP_CACHE
    override = os.environ.get("PS2COOP_DESKTOP_DIR")
    if override:
        path = Path(override).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return [path]

    now = time.time()
    if _DESKTOP_CACHE and now - _DESKTOP_CACHE[0] < 20:
        return _DESKTOP_CACHE[1]

    dirs: list[Path] = []
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "[Environment]::GetFolderPath('Desktop')",
                ],
                text=True,
                capture_output=True,
                timeout=8,
                stdin=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
            if result.stdout.strip():
                dirs.append(Path(result.stdout.strip()))
        except Exception:
            pass
        home = Path.home()
        for candidate in (home / "Desktop", home / "OneDrive" / "Desktop", home / "Área de trabalho"):
            if candidate.is_dir():
                dirs.append(candidate)
        if not dirs:
            fallback = home / "Desktop"
            fallback.mkdir(parents=True, exist_ok=True)
            dirs.append(fallback)
        _DESKTOP_CACHE = (now, dirs)
        return dirs

    try:
        result = subprocess.run(
            ["xdg-user-dir", "DESKTOP"],
            text=True,
            capture_output=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        candidate = Path((result.stdout or "").strip())
        if candidate.is_dir():
            dirs.append(candidate)
    except Exception:
        pass
    for name in ("Desktop", "Área de trabalho", "Area de trabalho", "Ambiente de trabalho", "Escritorio"):
        candidate = Path.home() / name
        if candidate.is_dir():
            dirs.append(candidate)
    if not dirs:
        fallback = Path.home() / "Desktop"
        fallback.mkdir(parents=True, exist_ok=True)
        dirs.append(fallback)
    _DESKTOP_CACHE = (now, dirs)
    return dirs


def _launch_target() -> tuple[Path, list[str]]:
    if getattr(sys, "frozen", False):
        appimage = os.environ.get("APPIMAGE")
        if appimage:
            candidate = Path(appimage).expanduser()
            if candidate.is_file():
                return candidate.resolve(), []
        return Path(sys.executable).resolve(), []
    app_path = app_root() / "app.py"
    if IS_WINDOWS:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        exe = pythonw if pythonw.is_file() else Path(sys.executable)
        return exe, [str(app_path)]
    return Path(sys.executable), [str(app_path)]


def _desktop_quote(value: str) -> str:
    """Quoting do campo Exec (Desktop Entry Specification)."""
    value = value.replace("%", "%%")
    if re.fullmatch(r"[A-Za-z0-9_./:@+=-]+", value):
        return value
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


def _desktop_entry(title: str, game_dir: Path) -> str:
    target, prefix = _launch_target()
    args = [*prefix, "--game", str(game_dir)]
    command = " ".join(_desktop_quote(str(part)) for part in [str(target), *args])
    icon = _icon(("icon.png", "icon.svg"))
    icon_line = f"Icon={icon}\n" if icon else ""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={safe_title(title)} — {APP_NAME}\n"
        "Comment=Servidor local de co-op PS2\n"
        f"Exec={command}\n"
        f"Path={game_dir}\n"
        f"{icon_line}"
        "Terminal=false\n"
        "Categories=Game;Emulator;\n"
        "StartupNotify=false\n"
        f"X-PS2Coop-Game={game_dir}\n"
    )


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _windows_shortcut(title: str, game_dir: Path, desktop: Path) -> Path:
    target, prefix = _launch_target()
    args = subprocess.list2cmdline([*prefix, "--game", str(game_dir)])
    shortcut = desktop / f"{safe_title(title)}.lnk"
    icon = _icon(("icon.ico", "icon.png"))
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "$ws = New-Object -ComObject WScript.Shell\n"
        f"$sc = $ws.CreateShortcut({_ps_quote(str(shortcut))})\n"
        f"$sc.TargetPath = {_ps_quote(str(target))}\n"
        f"$sc.Arguments = {_ps_quote(args)}\n"
        f"$sc.WorkingDirectory = {_ps_quote(str(game_dir))}\n"
        f"$sc.Description = {_ps_quote(APP_NAME + ' — servidor local de co-op PS2')}\n"
        + (f"$sc.IconLocation = {_ps_quote(str(icon) + ',0')}\n" if icon else "")
        + "$sc.Save()\n"
    )
    script_path = profile_root(game_dir) / "create-shortcut.ps1"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8-sig")
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            text=True,
            capture_output=True,
            timeout=30,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip()[:500])
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass
    return shortcut


def create(game_dir: Path, title: str) -> dict[str, Any]:
    """Cria o atalho. Retorna os caminhos criados."""
    title = safe_title(title)
    if IS_WINDOWS:
        created: list[str] = []
        for desktop in _desktop_dirs()[:1]:
            created.append(str(_windows_shortcut(title, game_dir, desktop)))
        if not created:
            raise RuntimeError("Área de trabalho não encontrada.")
        return {"ok": True, "paths": created}

    entry = _desktop_entry(title, game_dir)
    slug = f"{APP_ID}-{slugify(title)}"
    created: list[str] = []
    targets: list[Path] = []
    for desktop in _desktop_dirs()[:1]:
        targets.append(desktop / f"{slug}.desktop")
    applications = Path.home() / ".local" / "share" / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    targets.append(applications / f"{slug}.desktop")

    icon = _icon(("icon.png", "icon.svg"))
    if icon:
        icons_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"
        icons_dir.mkdir(parents=True, exist_ok=True)
        try:
            if icon.suffix.lower() == ".png":
                (icons_dir / f"{APP_ID}.png").write_bytes(icon.read_bytes())
            else:
                (icons_dir / f"{APP_ID}.svg").write_bytes(icon.read_bytes())
        except OSError:
            pass

    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry, encoding="utf-8")
        path.chmod(0o755)
        created.append(str(path))
        try:
            subprocess.run(
                ["gio", "set", str(path), "metadata::trusted", "true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            pass
    try:
        subprocess.run(
            ["update-desktop-database", str(applications)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:
        pass
    return {"ok": True, "paths": created}


def existing(game_dir: Path, title: str) -> bool:
    title = safe_title(title)
    if IS_WINDOWS:
        return any((desktop / f"{title}.lnk").is_file() for desktop in _desktop_dirs())
    slug = f"{APP_ID}-{slugify(title)}.desktop"
    return any((desktop / slug).is_file() for desktop in _desktop_dirs())


def exists(game_dir: Path, title: str) -> bool:
    return existing(game_dir, title)


def remove(title: str) -> None:
    """Remove atalhos antigos deste app (usado quando o título muda)."""
    title = safe_title(title)
    targets: list[Path] = []
    if IS_WINDOWS:
        targets = [desktop / f"{title}.lnk" for desktop in _desktop_dirs()]
    else:
        slug = f"{APP_ID}-{slugify(title)}.desktop"
        targets = [desktop / slug for desktop in _desktop_dirs()]
        targets.append(Path.home() / ".local" / "share" / "applications" / slug)
    for path in targets:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue
