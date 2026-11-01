"""Integração com o MoonlightWeb: instalação, status, links e convites."""

from __future__ import annotations

import json
import os
import platform
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import (
    IS_WINDOWS,
    downloads_root,
    logs_root,
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

MOONLIGHT_VERSION = "0.4.1"
DEB_URL = (
    "https://github.com/linckosz/moonlight-web/releases/download/"
    f"v{MOONLIGHT_VERSION}/moonlightweb-{MOONLIGHT_VERSION}-linux-x64.deb"
)
RPM_URL = (
    "https://github.com/linckosz/moonlight-web/releases/download/"
    f"v{MOONLIGHT_VERSION}/moonlightweb-{MOONLIGHT_VERSION}-linux-x64.rpm"
)
WINDOWS_URL = (
    "https://github.com/linckosz/moonlight-web/releases/download/"
    f"v{MOONLIGHT_VERSION}/MoonlightWeb-installer-{MOONLIGHT_VERSION}-win-x64.exe"
)
FALLBACK_SHA256 = {
    "deb": "d88a86163f94033e3fef5fe95eadae3bdbba843e144332e4b9775423d21db495",
    "rpm": "11690a4f2b6a90d92b9559b01d199e08c1680bed7a2ee2867738edd19ec10a52",
    "win-x64": "fc6cf19ab7a7fe29d6314d58741f389738614b35b6ce0687eda0887e8f9c608b",
    "win-arm64": "4cd4ab1d1a7a2c61ebab6b4f3350afe598215d871e2622fb6182f251ae7cf8f2",
}

HOST_UUID = "moonlightweb-native-host"
LOCAL_APP_ID = 1
_SSL_CTX = ssl._create_unverified_context()
_STATUS_CACHE: dict[str, tuple[float, Any]] = {}
_STATUS_LOCK = threading.Lock()
_APP_ID_CACHE: tuple[float, int] = (0.0, LOCAL_APP_ID)
_INVITES_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_LAN_ONLY = os.environ.get("MW_LAN_ONLY", "").strip().lower() in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Configuração e processo
# ---------------------------------------------------------------------------

def settings_paths() -> list[Path]:
    home = Path.home()
    if IS_WINDOWS:
        roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [
            roaming / "MoonlightWeb" / "MoonlightWeb" / "settings.json",
            local / "MoonlightWeb" / "MoonlightWeb" / "settings.json",
        ]
    if platform.system() == "Darwin":
        return [home / "Library" / "Application Support" / "MoonlightWeb" / "MoonlightWeb" / "settings.json"]
    return [
        home / ".local" / "share" / "MoonlightWeb" / "MoonlightWeb" / "settings.json",
        home / ".local" / "share" / "MoonlightWeb" / "MoonlightWeb-dev" / "settings.json",
        home / ".config" / "MoonlightWeb" / "settings.json",
    ]


def settings() -> dict[str, Any]:
    for path in settings_paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            continue
    return {}


def find() -> Path | None:
    if IS_WINDOWS:
        candidates = [
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "MoonlightWeb" / "MoonlightWeb.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "MoonlightWeb" / "MoonlightWeb.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MoonlightWeb" / "MoonlightWeb.exe",
        ]
        for candidate in candidates:
            if candidate and candidate.is_file():
                return candidate
        return executable_on_path("MoonlightWeb.exe")

    candidates = [
        Path("/usr/bin/moonlightweb"),
        Path("/usr/local/bin/moonlightweb"),
        Path("/opt/moonlightweb/bin/MoonlightWeb"),
        Path("/opt/moonlightweb/moonlightweb"),
        tools_root() / "moonlight" / "MoonlightWeb.AppImage",
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return executable_on_path("moonlightweb")


def installed() -> bool:
    return find() is not None


def can_host() -> bool:
    """No Linux, só o pacote instalado (.deb/.rpm/AUR) captura a própria tela."""
    if IS_WINDOWS:
        return installed()
    exe = find()
    if not exe:
        return False
    return exe.suffix.lower() != ".appimage"


def log_path() -> Path:
    path = logs_root() / "moonlight.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def configured_https_port() -> int:
    try:
        return int(settings().get("https_port") or 443)
    except (TypeError, ValueError):
        return 443


def configured_http_port() -> int:
    try:
        return int(settings().get("http_port") or 80)
    except (TypeError, ValueError):
        return 80


def port_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _server_port_candidates() -> list[int]:
    candidates = [configured_https_port(), 443, 8443, 44729]
    result: list[int] = []
    for port in candidates:
        if 0 < port < 65536 and port not in result:
            result.append(port)
    return result


def _request(
    path: str,
    method: str = "GET",
    payload: Any = None,
    port: int | None = None,
    host_header: str = "localhost",
    forwarded_host: str = "",
    timeout: int = 12,
) -> dict[str, Any]:
    actual_port = port or active_port()
    data = None
    headers = {"Host": host_header, "Accept": "application/json", "User-Agent": "PS2Co-op/1.0"}
    if forwarded_host:
        headers["X-Forwarded-Host"] = forwarded_host
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"https://127.0.0.1:{actual_port}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, context=_SSL_CTX, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw else {}


def server_probe(force: bool = False) -> dict[str, Any] | None:
    """Descobre a porta HTTPS realmente ativa e confirma que é o MoonlightWeb."""
    if not installed():
        return None
    now = time.time()
    with _STATUS_LOCK:
        cached = _STATUS_CACHE.get("probe")
        if cached and not force and now - cached[0] < 4:
            return cached[1]

    found: dict[str, Any] | None = None
    for port in _server_port_candidates():
        if not port_open(port):
            continue
        try:
            info = _request("/api/server/status", port=port, timeout=3)
        except Exception:
            continue
        if (
            isinstance(info, dict)
            and info.get("status") == "running"
            and ("sharing" in info or "version" in info)
        ):
            info = dict(info)
            info["active_port"] = port
            found = info
            break

    with _STATUS_LOCK:
        _STATUS_CACHE["probe"] = (now, found)
    return found


def running() -> bool:
    return server_probe() is not None


def active_port() -> int:
    probe = server_probe()
    if probe and probe.get("active_port"):
        return int(probe["active_port"])
    return configured_https_port()


def https_port() -> int:
    return active_port()


def http_port() -> int:
    probe = server_probe()
    if probe and probe.get("http_port"):
        try:
            return int(probe["http_port"])
        except (TypeError, ValueError):
            pass
    return configured_http_port()


def _cache_get(key: str, max_age: float) -> Any | None:
    now = time.time()
    with _STATUS_LOCK:
        cached = _STATUS_CACHE.get(key)
        if cached and now - cached[0] < max_age:
            return cached[1]
    return None


def _cache_put(key: str, value: Any) -> None:
    with _STATUS_LOCK:
        _STATUS_CACHE[key] = (time.time(), value)


def clear_cache() -> None:
    with _STATUS_LOCK:
        _STATUS_CACHE.clear()
        _INVITES_CACHE.clear()


def start(job: Job | None = None) -> bool:
    if server_probe(force=True):
        return True
    exe = find()
    if not exe:
        raise RuntimeError("MoonlightWeb não instalado.")
    if not can_host():
        raise RuntimeError(
            "O MoonlightWeb portátil (AppImage) não captura a tela local. "
            "Instale o pacote .deb/.rpm do sistema."
        )

    log = log_path().open("ab")
    log.write(f"\n\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} iniciando MoonlightWeb ===\n".encode())
    log.flush()
    kwargs: dict[str, Any] = {
        "stdout": log,
        "stderr": log,
        "stdin": subprocess.DEVNULL,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    if job:
        job.message = "Iniciando MoonlightWeb…"
        job.progress = -1
    try:
        process = subprocess.Popen([str(exe), "--autostart"], **kwargs)
    finally:
        log.close()

    deadline = time.time() + 35
    while time.time() < deadline:
        if process.poll() is not None:
            break
        if server_probe(force=True):
            if job:
                job.message = "MoonlightWeb pronto"
                job.progress = 1.0
            return True
        time.sleep(0.6)

    tail = ""
    try:
        tail = log_path().read_text(encoding="utf-8", errors="replace")[-1200:].strip()
    except OSError:
        pass
    raise RuntimeError(
        "MoonlightWeb não abriu a porta HTTPS. Abra-o manualmente uma vez."
        + (f" Log: {tail}" if tail else "")
    )


# ---------------------------------------------------------------------------
# Instalação
# ---------------------------------------------------------------------------

def _release_url(kind: str) -> tuple[str, str, str]:
    """(versão, url, sha256) para o pacote pedido, com fallback fixo."""
    release = github_release("linckosz/moonlight-web")
    version = str((release or {}).get("tag_name") or MOONLIGHT_VERSION).lstrip("v") or MOONLIGHT_VERSION
    suffix = {
        "deb": "linux-x64.deb",
        "rpm": "linux-x64.rpm",
        "win-x64": "win-x64.exe",
        "win-arm64": "win-arm64.exe",
    }[kind]
    asset = release_asset(release, lambda name: name.endswith(suffix))
    fallback = {
        "deb": DEB_URL,
        "rpm": RPM_URL,
        "win-x64": WINDOWS_URL,
        "win-arm64": WINDOWS_URL.replace("win-x64", "win-arm64"),
    }[kind]
    return version, asset_url(asset, fallback), asset_digest(asset) or FALLBACK_SHA256.get(kind, "")


def _linux_family() -> str:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    data: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip().strip('"')
    return " ".join([data.get("ID", ""), data.get("ID_LIKE", "")]).lower()


def _privileged_prefix() -> list[str]:
    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    if executable_on_path("pkexec"):
        return ["pkexec"]
    sudo = executable_on_path("sudo")
    if sudo:
        probe = run_command([str(sudo), "-n", "true"], timeout=5)
        if probe.returncode == 0:
            return [str(sudo), "-n"]
    raise RuntimeError(
        "Não foi possível pedir permissão de administrador. "
        "Instale o MoonlightWeb manualmente pelo site oficial."
    )


def _run_privileged(command: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    full = [*_privileged_prefix(), *command]
    return run_command(full, timeout=timeout)


def install_linux(job: Job) -> Path:
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError(
            "O pacote oficial do MoonlightWeb para Linux é x64. Neste sistema ARM, "
            "instale pelo site oficial e use um PCSX2 nativo da distribuição."
        )
    family = _linux_family()
    if any(token in family for token in ("bazzite", "steamos", "silverblue", "kinoite")):
        raise RuntimeError(
            "Este sistema é imutável. Use o guia oficial do MoonlightWeb para Linux "
            "(camada rpm-ostree ou imagem com o pacote) e clique em Preparar novamente."
        )
    if any(token in family for token in ("arch", "manjaro", "endeavour", "garuda")):
        raise RuntimeError(
            "Nesta distribuição instale o MoonlightWeb pelo AUR: paru -S moonlightweb-bin "
            "(o AppImage não captura a tela local). Depois clique em Preparar novamente."
        )

    if executable_on_path("rpm-ostree") and "fedora" in family:
        raise RuntimeError(
            "Este sistema é imutável (Silverblue/Kinoite/Bazzite). Instale o MoonlightWeb "
            "por camada com: sudo rpm-ostree install moonlightweb  (ou use o guia oficial)."
        )

    if any(token in family for token in ("debian", "ubuntu", "mint", "pop", "zorin", "elementary", "kali")):
        version, url, digest = _release_url("deb")
        package = downloads_root() / f"moonlightweb-{version}-linux-x64.deb"
        job.message = "Baixando MoonlightWeb (.deb)…"
        download(url, package, job, expected_sha256=digest)
        job.message = "Autorize a instalação na janela do sistema…"
        job.progress = -1
        result = _run_privileged(["apt-get", "install", "-y", str(package)])
        if result.returncode != 0:
            raise RuntimeError(
                "apt-get falhou. Instale manualmente: sudo apt install "
                f"{package}  ({(result.stderr or result.stdout).strip()[:300]})"
            )
    elif any(token in family for token in ("fedora", "rhel", "centos", "rocky", "alma", "nobara", "suse")):
        version, url, digest = _release_url("rpm")
        package = downloads_root() / f"moonlightweb-{version}-linux-x64.rpm"
        job.message = "Baixando MoonlightWeb (.rpm)…"
        download(url, package, job, expected_sha256=digest)
        job.message = "Autorize a instalação na janela do sistema…"
        job.progress = -1
        if "suse" in family:
            command = ["zypper", "--non-interactive", "install", "--allow-unsigned-rpm", str(package)]
        else:
            command = ["dnf", "install", "-y", str(package)]
        result = _run_privileged(command)
        if result.returncode != 0:
            raise RuntimeError(f"Instalação do RPM falhou: {(result.stderr or result.stdout).strip()[:300]}")
    else:
        raise RuntimeError(
            "Distribuição não reconhecida. Instale o MoonlightWeb pelo site oficial: "
            "https://moonlightweb.top/guides/linux.html"
        )

    clear_cache()
    exe = find()
    if not exe or not can_host():
        raise RuntimeError("MoonlightWeb foi instalado, mas o pacote nativo não foi encontrado.")
    job.progress = 1.0
    job.message = "MoonlightWeb instalado"
    return exe


def _windows_installer_path(kind: str) -> Path:
    version, url, digest = _release_url(kind)
    return downloads_root() / f"MoonlightWeb-{version}-{kind}.exe"


def install_windows(job: Job) -> Path:
    kind = "win-arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "win-x64"
    installer = _windows_installer_path(kind)
    version, url, digest = _release_url(kind)
    job.message = "Baixando MoonlightWeb…"
    download(url, installer, job, expected_sha256=digest)
    job.message = "Instalando MoonlightWeb (pode pedir permissão)…"
    job.progress = -1
    # O instalador é Inno Setup. Silencioso primeiro; se não aparecer, abre
    # o assistente uma vez para o usuário concluir.
    result = run_command(
        [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"],
        timeout=900,
    )
    deadline = time.time() + 20
    exe = find()
    while not exe and time.time() < deadline:
        time.sleep(1)
        exe = find()
    if not exe:
        subprocess.run([str(installer)], check=False)
        exe = find()
    if not exe:
        raise RuntimeError(
            "A instalação do MoonlightWeb não foi concluída. "
            f"Execute manualmente {installer} e clique em Preparar de novo."
        )
    clear_cache()
    job.progress = 1.0
    job.message = "MoonlightWeb instalado"
    return exe


def install(job: Job) -> Path:
    if installed() and can_host():
        job.progress = 1.0
        job.message = "MoonlightWeb já está instalado"
        return find()  # type: ignore[return-value]
    return install_windows(job) if IS_WINDOWS else install_linux(job)


# ---------------------------------------------------------------------------
# API local
# ---------------------------------------------------------------------------

def _lan_host_header(port: int | None = None) -> str:
    actual = port or https_port()
    ip = lan_ip()
    return f"{ip}:{actual}" if actual != 443 else ip


def lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        finally:
            sock.close()
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def share_status() -> dict[str, Any]:
    cached = _cache_get("share_status", 2.0)
    if cached is not None:
        return cached
    status = _request(f"/api/share/status?host={HOST_UUID}")
    _cache_put("share_status", status)
    return status


def display_app_id() -> int:
    global _APP_ID_CACHE
    now = time.time()
    if now - _APP_ID_CACHE[0] < 60:
        return _APP_ID_CACHE[1]
    app_id = LOCAL_APP_ID
    try:
        data = _request(
            f"/api/hosts/{HOST_UUID}/apps?client_uniqueid=ps2coop",
            timeout=10,
        )
        apps = data.get("apps") if isinstance(data, dict) else None
        if isinstance(apps, list):
            displays = [
                int(app.get("id"))
                for app in apps
                if isinstance(app, dict) and 0 < int(app.get("id") or 0) < 1000
            ]
            if displays:
                app_id = displays[0]
    except Exception:
        pass
    _APP_ID_CACHE = (now, app_id)
    return app_id


def _slot_permissions(gamepad: bool = True) -> dict[str, Any]:
    return {"gamepad": gamepad, "keyboardMouse": False, "hid": False}


def _invite_from_slot(
    slot: dict[str, Any],
    credential: dict[str, Any] | None = None,
    first_player: int = 2,
) -> dict[str, Any]:
    devices = slot.get("devices") or []
    state = str(slot.get("state") or "off")
    streaming = bool(slot.get("streaming"))
    slot_number = int(slot.get("slot") or 2)
    player_number = max(1, slot_number - 2 + max(1, int(first_player)))
    invite = {
        "slot": slot_number,
        "player": player_number,
        "state": state,
        "devices": len(devices),
        "streaming": streaming,
        "connected": streaming,
        "url": "",
        "pin": "",
        "name": f"Jogador {player_number}",
        "reach": "",
        "local_only": False,
        "access": slot.get("access_level", "viewer"),
        "permissions": slot.get("permissions") or {},
    }
    if credential:
        if credential.get("url"):
            invite["url"] = str(credential.get("url"))
        if credential.get("pin"):
            invite["pin"] = str(credential.get("pin"))
        invite["reach"] = str(credential.get("reach") or "")
        invite["local_only"] = bool(credential.get("local_only"))
    return invite


def get_invites(
    create: bool = False,
    link_address: str = "auto",
    count: int = 3,
    first_player: int = 2,
) -> list[dict[str, Any]]:
    """Lista (e opcionalmente cria) um convite por jogador remoto."""
    wanted = max(0, min(3, int(count)))
    first_player = max(1, min(4, int(first_player)))
    if wanted == 0:
        return []

    cache_key = f"invites:{create}:{link_address}:{wanted}:{first_player}"
    if not create:
        cached = _INVITES_CACHE.get(cache_key)
        if cached and time.time() - cached[0] < 2.5:
            return cached[1]

    status = share_status()
    slots = {int(slot.get("slot") or 0): slot for slot in status.get("slots", [])}
    app_id = display_app_id() if create else LOCAL_APP_ID

    if create:
        try:
            _request(
                "/api/share/link-address",
                "POST",
                {"host_uuid": HOST_UUID, "link_address": link_address or "auto"},
            )
        except Exception:
            pass
        try:
            _request("/api/share/feed", "POST", {"height": 720})
        except Exception:
            pass

    invites: list[dict[str, Any]] = []
    forwarded_host = _lan_host_header()
    for slot_number in range(2, 2 + wanted):
        slot = slots.get(slot_number) or {"slot": slot_number, "state": "off", "devices": []}
        state = str(slot.get("state") or "off")
        credential: dict[str, Any] | None = None

        if create:
            try:
                _request(
                    f"/api/share/slots/{slot_number}/permissions",
                    "POST",
                    _slot_permissions(True),
                )
                _request(
                    f"/api/share/slots/{slot_number}/name",
                    "POST",
                    {"name": f"Jogador {slot_number - 2 + first_player}"},
                )
                _request(
                    f"/api/share/slots/{slot_number}/ttl",
                    "POST",
                    {"ttl_secs": 86400},
                )
            except Exception:
                pass
            if state != "off":
                try:
                    _request(f"/api/share/slots/{slot_number}/deactivate", "POST", {})
                except Exception:
                    pass
            try:
                credential = _request(
                    f"/api/share/slots/{slot_number}/activate",
                    "POST",
                    {"host_uuid": HOST_UUID, "app_id": app_id, "ttl_secs": 86400},
                    forwarded_host=forwarded_host,
                )
            except Exception as exc:
                # Um app_id que não existe mais não pode impedir o convite:
                # tenta o id de display padrão uma vez.
                if app_id != LOCAL_APP_ID:
                    try:
                        credential = _request(
                            f"/api/share/slots/{slot_number}/activate",
                            "POST",
                            {"host_uuid": HOST_UUID, "app_id": LOCAL_APP_ID, "ttl_secs": 86400},
                            forwarded_host=forwarded_host,
                        )
                    except Exception:
                        raise exc
                else:
                    raise
            if credential:
                try:
                    _request(
                        f"/api/share/slots/{slot_number}/name",
                        "POST",
                        {"name": f"Jogador {slot_number - 2 + first_player}"},
                    )
                except Exception:
                    pass
                slot = {
                    **slot,
                    "state": credential.get("state") or "shared",
                    "name": credential.get("name") or slot.get("name"),
                    "permissions": credential.get("permissions") or _slot_permissions(True),
                    "access_level": credential.get("access_level", "gamer"),
                }
        elif state != "off":
            try:
                credential = _request(
                    f"/api/share/slots/{slot_number}/credentials",
                    "POST",
                    {},
                    forwarded_host=forwarded_host,
                )
            except Exception:
                credential = None
            if credential and credential.get("available") is False:
                credential = None

        invites.append(_invite_from_slot(slot, credential, first_player))

    if create:
        # Convites antigos de uma sessão com mais jogadores não podem continuar
        # abertos em segundo plano.
        for extra in range(2 + wanted, 5):
            try:
                _request(f"/api/share/slots/{extra}/deactivate", "POST", {})
            except Exception:
                pass
        clear_cache()
    else:
        _INVITES_CACHE[cache_key] = (time.time(), invites)
    return invites


def revoke_beyond(needed: int) -> None:
    """Fecha convites de slots que não são mais usados pela sessão atual."""
    if not installed() or not running():
        return
    for slot in range(2 + max(0, min(3, int(needed))), 5):
        try:
            _request(f"/api/share/slots/{slot}/deactivate", "POST", {})
        except Exception:
            pass
    clear_cache()


def revoke_invites() -> dict[str, Any]:
    if not installed():
        raise RuntimeError("MoonlightWeb não instalado.")
    if not running():
        start()
    for slot in (2, 3, 4):
        try:
            _request(f"/api/share/slots/{slot}/deactivate", "POST", {})
        except Exception:
            pass
    clear_cache()
    return {"ok": True}


def internet_status() -> dict[str, Any]:
    cached = _cache_get("internet_status", 5.0)
    if cached is not None:
        return cached
    try:
        data = _request("/api/internet/status", timeout=6)
    except Exception:
        data = {}
    _cache_put("internet_status", data)
    return data


def public_link() -> str:
    data = internet_status()
    rendezvous = data.get("rendezvous") or {}
    if isinstance(rendezvous, dict) and rendezvous.get("online") and rendezvous.get("url"):
        return str(rendezvous["url"])
    if _LAN_ONLY:
        return ""
    settings_data = settings()
    rendezvous_id = str(settings_data.get("rendezvous_id") or "")
    if settings_data.get("internet_access_enabled") and rendezvous_id:
        return f"https://stream.moonlightweb.top/{rendezvous_id}"
    return ""


def connection_info() -> dict[str, Any]:
    probe = server_probe()
    port = int(probe.get("active_port") or configured_https_port()) if probe else configured_https_port()
    inet = internet_status() if probe else {}
    ip = str(inet.get("local_ip") or lan_ip())
    local_ips = inet.get("local_ips") if isinstance(inet.get("local_ips"), list) else [ip]
    public = public_link() if probe else ""
    public_enabled = bool(inet.get("internet_access_enabled")) if probe else bool(settings().get("internet_access_enabled"))
    port_suffix = "" if port == 443 else f":{port}"
    return {
        "lan": f"https://{ip}{port_suffix}" if probe else "",
        "public": public,
        "public_enabled": public_enabled,
        "remote_reachable": bool((inet.get("rendezvous") or {}).get("online")) if probe else False,
        "public_ip": str(inet.get("public_ip") or ""),
        "local_ip": ip,
        "local_ips": local_ips,
        "port": port,
        "host_page": f"https://localhost{port_suffix}/",
        "admin_page": f"https://localhost{port_suffix}/admin",
        "version": str((probe or {}).get("version") or ""),
        "running": bool(probe),
    }


def open_admin() -> None:
    from .config import open_url

    open_url(connection_info()["admin_page"])


def open_host() -> None:
    from .config import open_url

    open_url(connection_info()["host_page"])
