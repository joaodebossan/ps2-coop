"""Descoberta de imagens de PS2 na pasta do jogo."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

IMAGE_EXTENSIONS = {".iso", ".chd", ".cso"}


@dataclass(frozen=True)
class GameImage:
    path: Path
    name: str
    title: str
    size: int
    extension: str

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


def title_from_filename(path: Path) -> str:
    stem = path.stem
    # Remove sufixos comuns de dump: "(USA)", "[SLUS-20973]", "(v2.00)" etc.
    stem = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", stem).strip()
    stem = re.sub(r"\s+", " ", stem)
    return stem or path.stem


def find_images(folder: Path) -> list[GameImage]:
    folder = folder.resolve()
    if not folder.is_dir():
        return []

    images: list[GameImage] = []
    for entry in folder.iterdir():
        try:
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            images.append(
                GameImage(
                    path=entry,
                    name=entry.name,
                    title=title_from_filename(entry),
                    size=entry.stat().st_size,
                    extension=entry.suffix.lower(),
                )
            )
        except OSError:
            continue

    images.sort(key=lambda item: item.name.lower())
    return images


def find_image_by_name(folder: Path, name: str) -> GameImage | None:
    for image in find_images(folder):
        if image.name == name:
            return image
    return None


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE).strip().lower()
    value = re.sub(r"[\s_-]+", "-", value)
    return value.strip("-") or "ps2-game"


def human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"
