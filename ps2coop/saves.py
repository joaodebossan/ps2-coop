"""Backups versionados dos memory cards por jogo."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from . import pcsx2
from .config import open_in_file_manager, profile_root


def saves_dir(game_dir: Path) -> Path:
    path = profile_root(game_dir) / "saves"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_backups(game_dir: Path) -> list[dict[str, Any]]:
    root = saves_dir(game_dir)
    result: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        files = list(entry.glob("*.ps2"))
        if not files:
            continue
        result.append(
            {
                "name": entry.name,
                "files": len(files),
                "size": sum(file.stat().st_size for file in files),
            }
        )
    return result


def backup(game_dir: Path) -> dict[str, Any]:
    if pcsx2.running(game_dir):
        raise RuntimeError("Feche o jogo antes de fazer backup do memory card.")
    memcards = pcsx2.memcards_dir(game_dir)
    files = list(memcards.glob("*.ps2"))
    if not files:
        raise RuntimeError("Nenhum memory card .ps2 encontrado para backup.")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = stamp
    target = saves_dir(game_dir) / name
    counter = 2
    while target.exists():
        name = f"{stamp}-{counter}"
        target = saves_dir(game_dir) / name
        counter += 1
    target.mkdir(parents=True, exist_ok=True)
    for file in files:
        shutil.copy2(file, target / file.name)
    ini = pcsx2.ini_path(game_dir)
    if ini.is_file():
        shutil.copy2(ini, target / "PCSX2.ini")
    return {"ok": True, "name": name, "files": len(files)}


def restore(game_dir: Path, name: str) -> dict[str, Any]:
    if not re.fullmatch(r"\d{8}-\d{6}(?:-\d+)?", name or ""):
        raise RuntimeError("Backup inválido.")
    source = saves_dir(game_dir) / name
    if not source.is_dir():
        raise RuntimeError("Backup não encontrado.")
    if pcsx2.running(game_dir):
        raise RuntimeError("Feche o jogo antes de restaurar um save.")

    try:
        backup(game_dir)
    except Exception:
        pass

    target = pcsx2.memcards_dir(game_dir)
    count = 0
    for file in source.glob("*.ps2"):
        shutil.copy2(file, target / file.name)
        count += 1
    backup_ini = source / "PCSX2.ini"
    if backup_ini.is_file():
        ini = pcsx2.ini_path(game_dir)
        ini.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_ini, ini)
    return {"ok": True, "name": name, "files": count}


def open_folder(game_dir: Path) -> None:
    open_in_file_manager(saves_dir(game_dir))
