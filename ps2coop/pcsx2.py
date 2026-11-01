"""PCSX2 portátil: instalação, BIOS, configuração de pads e execução."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import (
    IS_WINDOWS,
    downloads_root,
    logs_root,
    open_in_file_manager,
    profile_root,
    tools_root,
)
from .downloads import (
    Job,
    asset_digest,
    asset_url,
    download,
    executable_on_path,
    github_release,
    release_asset,
    run_command,
)

PCSX2_VERSION = "2.8.2"
FALLBACK_VERSION = PCSX2_VERSION
LINUX_APPIMAGE_URL = (
    "https://github.com/PCSX2/pcsx2/releases/download/"
    f"v{PCSX2_VERSION}/pcsx2-v{PCSX2_VERSION}-linux-appimage-x64-Qt.AppImage"
)
WINDOWS_INSTALLER_URL = (
    "https://github.com/PCSX2/pcsx2/releases/download/"
    f"v{PCSX2_VERSION}/pcsx2-v{PCSX2_VERSION}-windows-x64-installer.exe"
)
# Checksums das versões fixas de fallback (quando a API do GitHub não responde).
FALLBACK_SHA256 = {
    "linux": "0c46bb6a88aa2782b10853a7b07cf3387ba99cbef2b966372cd2315b8571abea",
    "windows": "3422f3705ccc641b7e4fdf3f280d635d05c3c8b53a56c3af55d9df115bdcf768",
}

PAD_TEMPLATE = """[Pad{n}]
Type = DualShock2
InvertL = 0
InvertR = 0
Deadzone = 0
AxisScale = 1.33
LargeMotorScale = 1
SmallMotorScale = 1
ButtonDeadzone = 0
PressureModifier = 0.5
Up = SDL-{sdl}/DPadUp
Right = SDL-{sdl}/DPadRight
Down = SDL-{sdl}/DPadDown
Left = SDL-{sdl}/DPadLeft
Triangle = SDL-{sdl}/FaceNorth
Circle = SDL-{sdl}/FaceEast
Cross = SDL-{sdl}/FaceSouth
Square = SDL-{sdl}/FaceWest
Select = SDL-{sdl}/Back
Start = SDL-{sdl}/Start
L1 = SDL-{sdl}/LeftShoulder
L2 = SDL-{sdl}/+LeftTrigger
R1 = SDL-{sdl}/RightShoulder
R2 = SDL-{sdl}/+RightTrigger
L3 = SDL-{sdl}/LeftStick
R3 = SDL-{sdl}/RightStick
LUp = SDL-{sdl}/-LeftY
LRight = SDL-{sdl}/+LeftX
LDown = SDL-{sdl}/+LeftY
LLeft = SDL-{sdl}/-LeftX
RUp = SDL-{sdl}/-RightY
RRight = SDL-{sdl}/+RightX
RDown = SDL-{sdl}/+RightY
RLeft = SDL-{sdl}/-RightX"""

BIOS_EXTENSIONS = {".bin", ".rom0", ".rom1", ".nvm", ".mec", ".inf", ".diff"}
_VERSION_CACHE: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Release / instalação
# ---------------------------------------------------------------------------

def _release_asset() -> tuple[str, str, str]:
    """(versão, url, sha256) da release mais recente, com fallback fixo."""
    release = github_release("PCSX2/pcsx2")
    version = str((release or {}).get("tag_name") or "").lstrip("v")
    wanted = "linux-appimage-x64-Qt.AppImage" if not IS_WINDOWS else "windows-x64-installer.exe"
    asset = release_asset(release, lambda name: name.endswith(wanted))
    if asset:
        return version or FALLBACK_VERSION, asset_url(asset, ""), asset_digest(asset)
    return (
        FALLBACK_VERSION,
        WINDOWS_INSTALLER_URL if IS_WINDOWS else LINUX_APPIMAGE_URL,
        FALLBACK_SHA256["windows" if IS_WINDOWS else "linux"],
    )


def _linux_appimage() -> Path:
    return tools_root() / "pcsx2" / "PCSX2.AppImage"


def _windows_exe() -> Path:
    return tools_root() / "pcsx2" / "pcsx2-qt.exe"


def _usable_executable(path: Path) -> bool:
    if not path.is_file():
        return False
    return os.name == "nt" or os.access(path, os.X_OK)


def find_executable() -> Path | None:
    """Procura o PCSX2 portátil e depois instalações do sistema."""
    if IS_WINDOWS:
        candidates = [
            _windows_exe(),
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "PCSX2" / "pcsx2-qt.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "PCSX2" / "pcsx2-qt.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "PCSX2" / "pcsx2-qt.exe",
        ]
        for candidate in candidates:
            if candidate and _usable_executable(candidate):
                return candidate
        portable_root = tools_root() / "pcsx2"
        if portable_root.is_dir():
            try:
                for candidate in portable_root.rglob("pcsx2-qt.exe"):
                    if _usable_executable(candidate):
                        return candidate
            except OSError:
                pass
        return executable_on_path("pcsx2-qt.exe")

    candidates = [
        _linux_appimage(),
        Path("/usr/bin/pcsx2-qt"),
        Path("/usr/local/bin/pcsx2-qt"),
        Path("/usr/games/pcsx2-qt"),
        Path("/usr/bin/pcsx2"),
        Path("/usr/local/bin/pcsx2"),
        Path("/snap/bin/pcsx2"),
        Path("/app/bin/pcsx2-qt"),
        Path("/var/lib/flatpak/exports/bin/net.pcsx2.PCSX2"),
        Path.home() / ".local" / "share" / "flatpak" / "exports" / "bin" / "net.pcsx2.PCSX2",
    ]
    for candidate in candidates:
        if _usable_executable(candidate):
            return candidate
    return executable_on_path("pcsx2-qt") or executable_on_path("pcsx2")


def installed() -> bool:
    return find_executable() is not None


def _version_file() -> Path:
    return tools_root() / "pcsx2" / "version.txt"


def _portable_version(exe: Path) -> str:
    try:
        if (tools_root() / "pcsx2") in exe.parents:
            stored = _version_file().read_text(encoding="utf-8", errors="replace").strip()
            return stored or PCSX2_VERSION
    except OSError:
        pass
    return ""


def version() -> str:
    exe = find_executable()
    if not exe:
        return ""
    key = str(exe)
    if key in _VERSION_CACHE:
        return _VERSION_CACHE[key]
    value = _portable_version(exe)
    if value:
        _VERSION_CACHE[key] = value
        return value
    try:
        env = os.environ.copy()
        appimage_env = _appimage_env()
        if appimage_env:
            env.update(appimage_env)
        result = run_command([str(exe), "-version"], timeout=12, env=env)
        text = (result.stdout or "") + (result.stderr or "")
        match = re.search(r"v?(\d+\.\d+\.\d+)", text)
        value = match.group(1) if match else ""
    except Exception:
        value = ""
    _VERSION_CACHE[key] = value
    return value


def _appimage_env() -> dict[str, str] | None:
    if not _linux_appimage().is_file():
        return None
    if os.access("/dev/fuse", os.R_OK | os.W_OK):
        return None
    env = os.environ.copy()
    env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    return env


def install(job: Job) -> Path:
    """Baixa o PCSX2 portátil. Linux: AppImage; Windows: instalador Inno silencioso."""
    current = find_executable()
    if current:
        job.message = "PCSX2 já está instalado"
        job.progress = 1.0
        return current

    if not IS_WINDOWS and os.uname().machine.lower() not in ("x86_64", "amd64"):
        raise RuntimeError(
            "O PCSX2 portátil oficial é x64. Neste Linux ARM, instale o PCSX2 pelo "
            "gerenciador de pacotes da distribuição e clique em Preparar de novo."
        )

    version_label, url, digest = _release_asset()
    if IS_WINDOWS:
        installer = downloads_root() / f"pcsx2-{version_label}-windows-x64-installer.exe"
        job.message = "Baixando PCSX2…"
        download(url, installer, job, expected_sha256=digest)
        target = tools_root() / "pcsx2"
        target.mkdir(parents=True, exist_ok=True)
        job.message = "Instalando PCSX2…"
        job.progress = -1
        result = run_command(
            [
                str(installer),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/NOICONS",
                f"/DIR={target}",
            ],
            timeout=900,
        )
        found = _windows_exe()
        if not found.is_file():
            candidates = list(target.rglob("pcsx2-qt.exe"))
            found = candidates[0] if candidates else found
        if not found.is_file() or result.returncode not in (0, 3010):
            raise RuntimeError(
                "A instalação do PCSX2 não terminou. "
                "Instale manualmente em https://pcsx2.net/downloads/ e abra o app de novo."
            )
        try:
            _version_file().write_text(version_label + "\n", encoding="utf-8")
        except OSError:
            pass
        job.progress = 1.0
        job.message = "PCSX2 instalado"
        return found

    appimage = _linux_appimage()
    job.message = "Baixando PCSX2 (AppImage)…"
    download(url, appimage, job, expected_sha256=digest)
    appimage.chmod(0o755)
    if not appimage.is_file() or appimage.stat().st_size < 10 * 1024 * 1024:
        raise RuntimeError("O PCSX2 AppImage baixado parece incompleto. Tente novamente.")
    try:
        _version_file().write_text(version_label + "\n", encoding="utf-8")
    except OSError:
        pass
    job.progress = 1.0
    job.message = "PCSX2 instalado"
    return appimage


# ---------------------------------------------------------------------------
# Dados por jogo
# ---------------------------------------------------------------------------

def datapath(game_dir: Path) -> Path:
    path = profile_root(game_dir) / "pcsx2"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_root(game_dir: Path) -> Path:
    return datapath(game_dir) / "PCSX2"


def ini_path(game_dir: Path) -> Path:
    return data_root(game_dir) / "inis" / "PCSX2.ini"


def bios_dir(game_dir: Path) -> Path:
    path = data_root(game_dir) / "bios"
    path.mkdir(parents=True, exist_ok=True)
    return path


def memcards_dir(game_dir: Path) -> Path:
    path = data_root(game_dir) / "memcards"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path(game_dir: Path) -> Path:
    path = profile_root(game_dir) / "logs" / "pcsx2.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def pid_path(game_dir: Path) -> Path:
    return profile_root(game_dir) / "pcsx2.pid"


def ensure_data(game_dir: Path) -> Path:
    """Roda -testconfig uma vez para o PCSX2 criar INI e pastas."""
    exe = find_executable()
    if not exe:
        raise RuntimeError("PCSX2 não instalado.")
    ini = ini_path(game_dir)
    if ini.exists():
        return ini

    env = os.environ.copy()
    if not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
        env["QT_QPA_PLATFORM"] = "offscreen"
    appimage_env = _appimage_env()
    if appimage_env:
        env.update(appimage_env)
    try:
        result = run_command(
            [str(exe), "-datapath", str(datapath(game_dir)), "-testconfig"],
            timeout=120,
            env=env,
        )
    except Exception as exc:
        raise RuntimeError(f"Não foi possível inicializar o PCSX2: {exc}") from exc

    if not ini.exists():
        detail = ((result.stdout or "") + (result.stderr or "")).strip()[-400:]
        raise RuntimeError(
            "O PCSX2 não criou o PCSX2.ini. Abra o PCSX2 uma vez e tente de novo."
            + (f" Detalhe: {detail}" if detail else "")
        )
    return ini


# ---------------------------------------------------------------------------
# INI
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"(?ms)^\[(?P<name>[^\]]+)\]\s*\n(?P<body>.*?)(?=^\[|\Z)")


def _section_bounds(text: str, section: str) -> tuple[int, int] | None:
    for match in _SECTION_RE.finditer(text):
        if match.group("name").strip() == section:
            return match.start(), match.end()
    return None


def _ensure_section(text: str, section: str) -> str:
    if _section_bounds(text, section):
        return text
    return text.rstrip() + f"\n\n[{section}]\n"


def _set_value(text: str, section: str, key: str, value: str) -> str:
    text = _ensure_section(text, section)
    bounds = _section_bounds(text, section)
    if not bounds:
        return text
    start, end = bounds
    body = text[start:end]
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")
    if pattern.search(body):
        body = pattern.sub(f"{key} = {value}", body, count=1)
    else:
        header_end = body.find("\n") + 1
        body = body[:header_end] + f"{key} = {value}\n" + body[header_end:]
    return text[:start] + body + text[end:]


def _get_value(text: str, section: str, key: str) -> str:
    bounds = _section_bounds(text, section)
    if not bounds:
        return ""
    start, end = bounds
    match = re.search(rf"(?m)^{re.escape(key)}\s*=\s*(.*)$", text[start:end])
    return match.group(1).strip() if match else ""


def _replace_section(text: str, section: str, body: str) -> str:
    text = _ensure_section(text, section)
    bounds = _section_bounds(text, section)
    if not bounds:
        return text
    start, end = bounds
    replacement = f"[{section}]\n{body.strip()}\n\n"
    # come o espaçamento anterior para não acumular linhas em branco
    before = text[:start].rstrip() + "\n\n"
    return before + replacement + text[end:].lstrip("\n")


def apply_pads_to_text(text: str, players: int, pad_map: dict[int, int] | None = None) -> str:
    players = max(1, min(4, int(players)))
    pad_sections = (1, 2, 6, 7)[:players]
    if pad_map is None:
        pad_map = {section: player - 1 for player, section in enumerate(pad_sections, start=1)}

    text = _set_value(text, "Pad", "MultitapPort1", "false")
    text = _set_value(text, "Pad", "MultitapPort2", "true" if players >= 3 else "false")
    text = _set_value(text, "InputSources", "SDL", "true")
    text = _set_value(text, "InputSources", "SDLControllerEnhancedMode", "true")

    for pad in range(1, 9):
        sdl = pad_map.get(pad)
        if pad in pad_sections and sdl is not None:
            body = PAD_TEMPLATE.format(n=pad, sdl=int(sdl))
            # PAD_TEMPLATE já inclui o cabeçalho; _replace_section espera o corpo.
            body = body.split("\n", 1)[1]
        else:
            body = "Type = None"
        text = _replace_section(text, f"Pad{pad}", body)
    return text


def apply_pads(game_dir: Path, players: int, pad_map: dict[int, int] | None = None) -> None:
    """Configura 1–4 controles (multitap no port 2 para 3–4)."""
    ini = ensure_data(game_dir)
    text = ini.read_text(encoding="utf-8", errors="replace")
    text = apply_pads_to_text(text, players, pad_map)
    ini.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# BIOS
# ---------------------------------------------------------------------------

def _has_bios_files(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        for entry in path.iterdir():
            try:
                if (
                    entry.is_file()
                    and entry.suffix.lower() in BIOS_EXTENSIONS
                    and entry.stat().st_size >= 1024 * 1024
                ):
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def _system_ini_paths() -> list[Path]:
    home = Path.home()
    if IS_WINDOWS:
        roots = [
            Path(os.environ.get("APPDATA", "")) / "PCSX2",
            Path(os.environ.get("LOCALAPPDATA", "")) / "PCSX2",
            home / "Documents" / "PCSX2",
        ]
    else:
        roots = [
            home / ".config" / "PCSX2",
            home / ".local" / "share" / "PCSX2",
            home / ".var" / "app" / "net.pcsx2.PCSX2" / "config" / "PCSX2",
            home / ".var" / "app" / "net.pcsx2.PCSX2" / "data" / "PCSX2",
            home / "snap" / "pcsx2" / "current" / ".config" / "PCSX2",
            home / "snap" / "pcsx2" / "current" / ".local" / "share" / "PCSX2",
            Path("/usr/share/pcsx2"),
            Path("/usr/local/share/pcsx2"),
        ]
    paths: list[Path] = []
    for root in roots:
        paths.extend([root / "inis" / "PCSX2.ini", root / "PCSX2.ini"])
    return [path for path in paths if path.is_file()]


def _bios_candidates_from_inis() -> list[Path]:
    result: list[Path] = []
    for ini in _system_ini_paths():
        try:
            text = ini.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        folder = _get_value(text, "Folders", "Bios")
        if not folder:
            continue
        path = Path(folder).expanduser()
        if not path.is_absolute():
            path = ini.parent.parent / path
        if _has_bios_files(path):
            result.append(path.resolve())
    return result


def bios_candidates() -> list[Path]:
    home = Path.home()
    candidates: list[Path] = []
    if IS_WINDOWS:
        candidates += [
            home / "Documents" / "PCSX2" / "bios",
            Path(os.environ.get("APPDATA", "")) / "PCSX2" / "bios",
            Path(os.environ.get("LOCALAPPDATA", "")) / "PCSX2" / "bios",
            tools_root() / "pcsx2" / "bios",
        ]
    else:
        candidates += [
            home / ".var" / "app" / "net.pcsx2.PCSX2" / "config" / "PCSX2" / "bios",
            home / ".var" / "app" / "net.pcsx2.PCSX2" / "data" / "PCSX2" / "bios",
            home / ".config" / "PCSX2" / "bios",
            home / ".local" / "share" / "PCSX2" / "bios",
            home / "snap" / "pcsx2" / "current" / ".config" / "PCSX2" / "bios",
            home / "snap" / "pcsx2" / "current" / ".local" / "share" / "PCSX2" / "bios",
            Path("/usr/share/pcsx2/bios"),
            tools_root() / "pcsx2" / "bios",
        ]
    candidates.extend(_bios_candidates_from_inis())
    result: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if _has_bios_files(path):
            result.append(path)
    return result


def _bios_name_from_dir(source: Path, source_ini: Path | None = None) -> str:
    if source_ini and source_ini.is_file():
        try:
            text = source_ini.read_text(encoding="utf-8", errors="replace")
            name = _get_value(text, "Filenames", "BIOS")
            if name and (source / name).is_file():
                return name
        except OSError:
            pass

    try:
        files = sorted(source.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        raise RuntimeError("Pasta de BIOS ilegível.") from exc
    bins = [f for f in files if f.suffix.lower() == ".bin" and f.stat().st_size >= 1024 * 1024]
    if bins:
        return bins[0].name
    roms = [f for f in files if f.suffix.lower() == ".rom0"]
    if roms:
        return roms[0].name
    raise RuntimeError("Nenhum arquivo de BIOS válido (.bin ou .ROM0) encontrado.")


def adopt_bios(game_dir: Path, source: Path, source_ini: Path | None = None) -> str:
    if not _has_bios_files(source):
        raise RuntimeError("A pasta selecionada não contém uma BIOS válida.")
    name = _bios_name_from_dir(source, source_ini)
    target = bios_dir(game_dir)
    for entry in source.iterdir():
        if entry.is_file():
            try:
                shutil.copy2(entry, target / entry.name)
            except OSError:
                continue
    set_bios_name(game_dir, name)
    return name


def save_bios_file(game_dir: Path, filename: str, data: bytes) -> str:
    name = Path(filename or "bios.bin").name
    name = re.sub(r"[\x00-\x1f]", "", name).strip()
    if IS_WINDOWS:
        name = re.sub(r'[<>:"/\\|?*]', "_", name).rstrip(" .")
    if not name:
        name = "bios.bin"
    suffix = Path(name).suffix.lower()
    if suffix not in (".bin", ".rom0"):
        raise RuntimeError("Envie um arquivo .bin (ou .ROM0) da BIOS do PS2.")
    if not (1024 * 1024 <= len(data) <= 8 * 1024 * 1024):
        raise RuntimeError("Tamanho de BIOS inválido (esperado entre 1 MB e 8 MB).")
    target = bios_dir(game_dir) / name
    target.write_bytes(data)
    set_bios_name(game_dir, name)
    return name


def find_and_adopt_bios(game_dir: Path) -> str:
    """Tenta importar automaticamente uma BIOS já usada por outro PCSX2."""
    for candidate in bios_candidates():
        try:
            return adopt_bios(game_dir, candidate)
        except Exception:
            continue
    return ""


def set_bios_name(game_dir: Path, name: str) -> None:
    ini = ensure_data(game_dir)
    text = ini.read_text(encoding="utf-8", errors="replace")
    text = _set_value(text, "Filenames", "BIOS", name)
    text = _set_value(text, "UI", "SetupWizardIncomplete", "false")
    ini.write_text(text, encoding="utf-8")


def bios_ok(game_dir: Path) -> bool:
    ini = ini_path(game_dir)
    if not ini.is_file():
        return False
    try:
        text = ini.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    name = _get_value(text, "Filenames", "BIOS")
    if not name:
        return False
    path = bios_dir(game_dir) / name
    try:
        return path.is_file() and path.stat().st_size >= 1024 * 1024
    except OSError:
        return False


def bios_name(game_dir: Path) -> str:
    try:
        text = ini_path(game_dir).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return _get_value(text, "Filenames", "BIOS")


def configure(game_dir: Path, players: int, pad_map: dict[int, int] | None = None) -> None:
    apply_pads(game_dir, players, pad_map)
    ini = ini_path(game_dir)
    text = ini.read_text(encoding="utf-8", errors="replace")
    text = _set_value(text, "UI", "SetupWizardIncomplete", "false" if bios_ok(game_dir) else "true")
    text = _set_value(text, "UI", "StartFullscreen", "true")
    text = _set_value(text, "UI", "ConfirmShutdown", "false")
    text = _set_value(text, "UI", "PauseOnFocusLoss", "false")
    text = _set_value(text, "UI", "HideMouseCursor", "true")
    text = _set_value(text, "UI", "InhibitScreensaver", "true")
    text = _set_value(text, "EmuCore", "EnableFastBoot", "true")
    text = _set_value(text, "EmuCore", "InhibitScreensaver", "true")
    text = _set_value(text, "EmuCore", "EnableDiscordPresence", "false")
    text = _set_value(text, "MemoryCards", "Slot1_Enable", "true")
    text = _set_value(text, "MemoryCards", "Slot1_Filename", "Mcd001.ps2")
    text = _set_value(text, "MemoryCards", "Slot2_Enable", "true")
    text = _set_value(text, "MemoryCards", "Slot2_Filename", "Mcd002.ps2")
    ini.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def _pid_command(pid: int) -> str:
    if IS_WINDOWS:
        return ""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").lower()
    except OSError:
        return ""


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        try:
            result = run_command(["tasklist", "/FI", f"PID eq {pid}", "/NH"], timeout=5)
            fields = (result.stdout or "").split()
            return len(fields) >= 2 and fields[1] == str(pid)
        except Exception:
            return False
    try:
        # Um processo filho morto fica como zumbi até ser colhido; os.kill(pid, 0)
        # continua respondendo. O estado em /proc/pid/stat diz a verdade.
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        state = stat.rsplit(")", 1)[1].split()[0] if ")" in stat else ""
        if state == "Z":
            return False
    except (OSError, IndexError):
        pass
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _is_our_process(pid: int, game_dir: Path) -> bool:
    if not _process_alive(pid):
        return False
    if IS_WINDOWS:
        try:
            result = run_command(["tasklist", "/FI", f"PID eq {pid}", "/NH"], timeout=5)
            fields = (result.stdout or "").split()
            return len(fields) >= 2 and fields[1] == str(pid) and "pcsx2" in fields[0].lower()
        except Exception:
            return False
    command = _pid_command(pid)
    if not command:
        return True
    return "pcsx2" in command or str(game_dir).lower() in command


def running(game_dir: Path) -> bool:
    path = pid_path(game_dir)
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if _is_our_process(pid, game_dir):
        return True
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return False


def start(
    game_dir: Path,
    image: Path,
    players: int,
    fullscreen: bool = True,
    pad_map: dict[int, int] | None = None,
) -> int:
    exe = find_executable()
    if not exe:
        raise RuntimeError("PCSX2 não instalado. Baixe o emulador primeiro.")
    if running(game_dir):
        raise RuntimeError("O PCSX2 já está rodando para este jogo.")

    configure(game_dir, players, pad_map)
    if not bios_ok(game_dir):
        raise RuntimeError("BIOS do PS2 não configurada. Envie o arquivo .bin da sua BIOS.")

    command = [
        str(exe),
        "-datapath",
        str(datapath(game_dir)),
        "-fullscreen" if fullscreen else "-nofullscreen",
        "-fastboot",
        "--",
        str(image),
    ]
    env = os.environ.copy()
    appimage_env = _appimage_env()
    if appimage_env:
        env.update(appimage_env)
    log_path(game_dir).parent.mkdir(parents=True, exist_ok=True)
    log = log_path(game_dir).open("ab")
    log.write(
        f"\n\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} iniciando {image.name} "
        f"({players}p) ===\n$ {' '.join(command)}\n".encode()
    )
    log.flush()

    kwargs: dict[str, Any] = {
        "stdout": log,
        "stderr": log,
        "stdin": subprocess.DEVNULL,
        "env": env,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    process = subprocess.Popen(command, **kwargs)
    log.close()
    pid_path(game_dir).write_text(str(process.pid), encoding="utf-8")
    time.sleep(0.8)
    if process.poll() is not None:
        tail = ""
        try:
            tail = log_path(game_dir).read_text(encoding="utf-8", errors="replace")[-1200:]
        except OSError:
            pass
        raise RuntimeError("O PCSX2 fechou logo após iniciar. " + (tail.strip() or "Veja os logs."))
    return process.pid


def stop(game_dir: Path) -> None:
    path = pid_path(game_dir)
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return

    if not _is_our_process(pid, game_dir):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return

    if IS_WINDOWS:
        try:
            run_command(["taskkill", "/PID", str(pid), "/T", "/F"], timeout=15)
        except Exception:
            pass
        deadline = time.time() + 10
        while time.time() < deadline and _process_alive(pid):
            time.sleep(0.2)
        if _process_alive(pid):
            raise RuntimeError(
                "O PCSX2 não encerrou. Feche a janela do emulador e tente de novo antes de copiar o save."
            )
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        deadline = time.time() + 8
        while time.time() < deadline and _process_alive(pid):
            time.sleep(0.2)
        if _process_alive(pid):
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except OSError:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
            deadline = time.time() + 4
            while time.time() < deadline and _process_alive(pid):
                time.sleep(0.2)
            if _process_alive(pid):
                raise RuntimeError("O PCSX2 não encerrou. Feche-o manualmente antes de copiar o save.")

    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def open_data_folder(game_dir: Path) -> None:
    open_in_file_manager(data_root(game_dir))


def open_logs_folder() -> None:
    open_in_file_manager(logs_root())
