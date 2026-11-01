"""Detecção e mapeamento de controles físicos e virtuais."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import IS_LINUX, IS_WINDOWS

GAMEPAD_NAME = re.compile(
    r"x-?box|gamepad|dualshock|dualsense|wireless controller|controller|joy-?con|8bitdo|"
    r"switch pro|pro controller|stadia|steam controller",
    re.I,
)
COMPANION_NAMES = ("motion sensors", "motion sensor", "touchpad", "touch pad", "accelerometer", "gyroscope")
VIRTUAL_NAME = re.compile(r"uinput|vigem|virtual|moonlight|vgamepad", re.I)

# PCSX2 usa o port 1 (pad 1) e o multitap do port 2 (pads 6 e 7).
PAD_SECTIONS = (1, 2, 6, 7)
_CACHE: tuple[float, list[Gamepad]] | None = None


@dataclass(frozen=True)
class Gamepad:
    index: int  # índice SDL/js
    name: str
    virtual: bool = False

    def to_json(self) -> dict[str, Any]:
        return {"index": self.index, "name": self.name, "virtual": self.virtual}


def _linux_devices() -> list[dict[str, Any]]:
    try:
        text = Path("/proc/bus/input/devices").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    devices: list[dict[str, Any]] = []
    for block in text.strip().split("\n\n"):
        item: dict[str, Any] = {"name": "", "handlers": [], "sysfs": ""}
        for line in block.splitlines():
            if line.startswith("N: Name="):
                item["name"] = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("H: Handlers="):
                item["handlers"] = line.split("=", 1)[1].split()
            elif line.startswith("S: Sysfs="):
                item["sysfs"] = line.split("=", 1)[1].strip()
        if item["name"]:
            devices.append(item)
    return devices


def _js_index(device: dict[str, Any]) -> int | None:
    for handler in device["handlers"]:
        if handler.startswith("js") and handler[2:].isdigit():
            return int(handler[2:])
    return None


def _is_joystick(device: dict[str, Any]) -> bool:
    return any(handler.startswith("js") for handler in device["handlers"])


def linux_gamepads() -> list[Gamepad]:
    pads: list[Gamepad] = []
    for device in _linux_devices():
        name = str(device["name"])
        low = name.lower()
        if any(skip in low for skip in COMPANION_NAMES):
            continue
        index = _js_index(device)
        if index is None or not _is_joystick(device):
            continue
        # uinput fica em /devices/virtual/input; Bluetooth real fica em
        # /devices/virtual/misc/uhid, então o prefixo precisa ser exato.
        virtual = str(device["sysfs"]).startswith("/devices/virtual/input/")
        if not virtual and VIRTUAL_NAME.search(name):
            virtual = True
        if not GAMEPAD_NAME.search(name) and not virtual:
            continue
        pads.append(Gamepad(index=index, name=name, virtual=virtual))
    pads.sort(key=lambda pad: (pad.index, pad.name.lower()))
    return pads


def _windows_names() -> list[str]:
    script = (
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.Name -match 'Xbox|Controller|Gamepad|DualSense|DualShock|8BitDo|"
        "Wireless Controller|Joy-Con|Pro Controller' } | "
        "Select-Object -ExpandProperty Name"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            text=True,
            capture_output=True,
            timeout=6,
            stdin=subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return sorted(set(names), key=str.lower)
    except Exception:
        return []


def windows_gamepads() -> list[Gamepad]:
    """No Windows o índice SDL não é exposto pelo PnP; a ordem é aproximada."""
    names = _windows_names()
    return [Gamepad(index=index, name=name, virtual=bool(VIRTUAL_NAME.search(name))) for index, name in enumerate(names)]


def detect_gamepads(force: bool = False) -> list[Gamepad]:
    """Lista os controles. No Windows o PowerShell é caro; usa cache curto."""
    global _CACHE
    now = time.time()
    ttl = 8.0 if IS_WINDOWS else 2.0
    if not force and _CACHE and now - _CACHE[0] < ttl:
        return list(_CACHE[1])
    if IS_LINUX:
        pads = linux_gamepads()
    elif IS_WINDOWS:
        pads = windows_gamepads()
    else:
        pads = []
    _CACHE = (now, pads)
    return list(pads)


def count_gamepads(pads: list[Gamepad] | None = None) -> tuple[int, int, list[str], list[str]]:
    """Retorna (virtuais, físicos, nomes virtuais, nomes físicos)."""
    pads = list(pads if pads is not None else detect_gamepads())
    virtual = [pad.name for pad in pads if pad.virtual]
    physical = [pad.name for pad in pads if not pad.virtual]
    return len(virtual), len(physical), virtual, physical


def build_pad_map(
    players: int,
    host_local: bool,
    pads: list[Gamepad] | None = None,
) -> dict[int, int]:
    """Mapeia seções de pad do PCSX2 para índices SDL.

    O host local deve jogar no pad 1, então o primeiro controle físico tem
    prioridade. Sem host local, os controles virtuais dos convidados vêm
    primeiro. O PCSX2 enumera o SDL na mesma ordem de /dev/input/jsN no Linux.
    """
    players = max(1, min(4, int(players)))
    pads = list(pads if pads is not None else detect_gamepads())

    physical = [pad for pad in pads if not pad.virtual]
    virtual = [pad for pad in pads if pad.virtual]
    if host_local:
        ordered = physical[:1] + virtual + physical[1:]
    else:
        ordered = virtual + physical

    selected: list[Gamepad] = []
    seen: set[int] = set()
    for pad in ordered:
        if pad.index in seen:
            continue
        seen.add(pad.index)
        selected.append(pad)
        if len(selected) >= players:
            break

    mapping: dict[int, int] = {}
    for pad_section, pad in zip(PAD_SECTIONS[:players], selected, strict=False):
        mapping[pad_section] = pad.index
    return mapping


def pad_map_description(
    players: int,
    host_local: bool,
    pads: list[Gamepad] | None = None,
    mapping: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    players = max(1, min(4, int(players)))
    pads = list(pads if pads is not None else detect_gamepads())
    mapping = mapping if mapping is not None else build_pad_map(players, host_local, pads)
    by_index = {pad.index: pad for pad in pads}
    result: list[dict[str, Any]] = []
    for player, section in enumerate(PAD_SECTIONS[:players], start=1):
        sdl = mapping.get(section)
        pad = by_index.get(sdl) if sdl is not None else None
        result.append(
            {
                "player": player,
                "pad": section,
                "sdl": sdl,
                "name": pad.name if pad else "",
                "virtual": bool(pad.virtual) if pad else False,
                "connected": pad is not None,
            }
        )
    return result
