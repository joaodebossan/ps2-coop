"""Caminhos, perfil e utilidades comuns do PS2 Co-op."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

APP_ID = "ps2coop"
APP_NAME = "PS2 Co-op"
VERSION = "1.0.1"

IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"

PROFILE_DIR_NAME = ".ps2coop"
AUTO_SETUP = os.environ.get("PS2COOP_AUTOSETUP", "1").lower() not in {"0", "false", "no", "off"}
MIN_PYTHON = (3, 10)


def app_root() -> Path:
    """Pasta do executável (ou do projeto, quando rodando do código).

    Num build de arquivo único do PyInstaller o executável fica ao lado da
    pasta do jogo — é ali que runtime/ e .ps2coop/ devem viver. Dentro de um
    AppImage, o executável real está num diretório temporário somente leitura;
    o arquivo .AppImage é que está na pasta do jogo.
    """
    if getattr(sys, "frozen", False):
        appimage = os.environ.get("APPIMAGE")
        if appimage:
            candidate = Path(appimage).expanduser()
            if candidate.is_file():
                return candidate.resolve().parent
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Onde ficam web/ e assets/ (PyInstaller usa _MEIPASS)."""
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled) if bundled else app_root()


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def user_data_root() -> Path:
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif IS_MACOS:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_ID


def tools_root() -> Path:
    """Ferramentas baixadas (PCSX2/MoonlightWeb)."""
    override = os.environ.get("PS2COOP_HOME")
    if override:
        path = Path(override).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    local = app_root() / "runtime"
    if _writable(local):
        return local

    fallback = user_data_root() / "runtime"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def downloads_root() -> Path:
    path = tools_root() / "downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_root() -> Path:
    path = tools_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_root(game_dir: Path) -> Path:
    return game_dir / PROFILE_DIR_NAME


def is_ps2coop_dir(path: Path) -> bool:
    return path.name == PROFILE_DIR_NAME and path.is_dir()


def load_profile(game_dir: Path) -> dict[str, Any]:
    path = profile_root(game_dir) / "profile.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def save_profile(game_dir: Path, data: dict[str, Any]) -> None:
    root = profile_root(game_dir)
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / "profile.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(root / "profile.json")


def game_dir_from_argv(argv: list[str] | None = None) -> Path:
    args = list(sys.argv[1:] if argv is None else argv)
    for index, value in enumerate(args):
        if value == "--game" and index + 1 < len(args):
            return Path(args[index + 1]).expanduser().resolve()
        if value.startswith("--game="):
            return Path(value.split("=", 1)[1]).expanduser().resolve()
    if getattr(sys, "frozen", False):
        # O usuário coloca o executável na pasta do jogo e dá dois cliques.
        # O diretório de trabalho do Windows Explorer nem sempre é o do .exe.
        appimage = os.environ.get("APPIMAGE")
        if appimage:
            candidate = Path(appimage).expanduser()
            if candidate.is_file():
                return candidate.resolve().parent
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def platform_label() -> str:
    if IS_WINDOWS:
        return "windows"
    if IS_MACOS:
        return "macos"
    return "linux"


def platform_name() -> str:
    labels = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}
    return labels.get(platform_label(), platform_label())


def machine_label() -> str:
    return platform.machine().lower()


def open_in_file_manager(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        if IS_WINDOWS:
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif IS_MACOS:
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
    except Exception as exc:  # noqa: BLE001 - chamada de conveniência
        raise RuntimeError(f"Não foi possível abrir a pasta: {exc}") from exc


def open_url(url: str) -> None:
    import webbrowser

    try:
        if not webbrowser.open(url):
            raise RuntimeError("Nenhum navegador disponível.")
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Não foi possível abrir o navegador: {exc}") from exc


def is_writable(path: Path) -> bool:
    return _writable(path)
