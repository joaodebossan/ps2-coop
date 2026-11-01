"""Servidor local e API do PS2 Co-op."""

from __future__ import annotations

import json
import mimetypes
import os
import platform
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import config, desktop, gamepads, moonlight, pcsx2, saves
from .config import (
    APP_ID,
    APP_NAME,
    VERSION,
    game_dir_from_argv,
    load_profile,
    logs_root,
    open_in_file_manager,
    open_url,
    platform_label,
    platform_name,
    profile_root,
    resource_root,
    save_profile,
)
from .downloads import Job, JobManager, read_json, write_json
from .games import find_image_by_name, find_images, human_size, title_from_filename

MAX_BIOS_SIZE = 8 * 1024 * 1024


def _console(text: str) -> None:
    try:
        if sys.stdout:
            sys.stdout.write(text + "\n")
            sys.stdout.flush()
    except Exception:
        pass


def _fatal(message: str) -> None:
    _console(message)
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)  # type: ignore[attr-defined]
        except Exception:
            pass
    raise SystemExit(1)


class AppState:
    def __init__(self, game_dir: Path, auto_setup: bool = True) -> None:
        self.game_dir = game_dir.resolve()
        if not self.game_dir.is_dir():
            raise RuntimeError(f"A pasta do jogo não existe: {self.game_dir}")
        self.auto_setup_enabled = bool(auto_setup and config.AUTO_SETUP)
        self.jobs = JobManager()
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(24)
        self.profile = load_profile(self.game_dir)
        self.profile.setdefault("version", 1)
        self.profile.setdefault("players", 2)
        self.profile.setdefault("host_local", False)
        self.profile.setdefault("shortcut", False)
        self.profile.setdefault("invite_network", "auto")
        self.profile.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
        if self.players() == 4 and not self.host_local():
            # MoonlightWeb compartilha no máximo 3 convidados.
            self.profile["players"] = 3
        self._shortcut_error = ""
        self._shortcut_error_title = ""
        self._auto_last_sig: tuple[Any, ...] | None = None
        self._ensure_image()
        self.save()
        self.maybe_shortcut()
        self.maybe_auto_setup()

    # -- perfil ---------------------------------------------------------
    def save(self) -> None:
        with self.lock:
            save_profile(self.game_dir, self.profile)

    def images(self) -> list[Any]:
        return find_images(self.game_dir)

    def image(self) -> Any | None:
        name = str(self.profile.get("image") or "")
        if name:
            found = find_image_by_name(self.game_dir, name)
            if found:
                return found
        images = self.images()
        return images[0] if images else None

    def _ensure_image(self) -> bool:
        """Sincroniza o perfil com a ISO atualmente escolhida na pasta."""
        image = self.image()
        changed = False
        if image:
            if self.profile.get("image") != image.name or not self.profile.get("title"):
                self.profile["title"] = image.title
                changed = True
            if self.profile.get("image") != image.name:
                self.profile["image"] = image.name
                changed = True
        else:
            if "image" in self.profile:
                self.profile.pop("image", None)
                changed = True
        return changed

    def title(self) -> str:
        image = self.image()
        return str(self.profile.get("title") or (image.title if image else self.game_dir.name))

    def players(self) -> int:
        try:
            return max(1, min(4, int(self.profile.get("players", 2))))
        except (TypeError, ValueError):
            return 2

    def host_local(self) -> bool:
        return bool(self.profile.get("host_local"))

    def invite_network(self) -> str:
        value = str(self.profile.get("invite_network") or "auto")
        return value if value in ("auto", "lan") else "auto"

    def set_players(self, players: int, host_local: bool) -> dict[str, Any]:
        if pcsx2.running(self.game_dir):
            raise RuntimeError("Pare o jogo antes de mudar a quantidade de jogadores ou o modo host.")
        players = max(1, min(4, int(players)))
        host_local = bool(host_local)
        if players == 4 and not host_local:
            raise RuntimeError(
                "Para 4 jogadores, ative “Host local”: o MoonlightWeb permite no máximo "
                "3 convidados e você ocupa o quarto controle."
            )
        with self.lock:
            self.profile["players"] = players
            self.profile["host_local"] = host_local
            self.save()
        moonlight.revoke_beyond(self.remote_players())
        return {"players": self.players(), "host_local": self.host_local()}

    def required_virtual(self) -> int:
        return self.players() - 1 if self.host_local() else self.players()

    def remote_players(self) -> int:
        return max(0, self.players() - (1 if self.host_local() else 0))

    def first_remote_player(self) -> int:
        return 2 if self.host_local() else 1

    # -- prontidão ------------------------------------------------------
    def core_ready(self) -> bool:
        return bool(self.image()) and pcsx2.installed() and moonlight.installed() and moonlight.can_host()

    def ready(self) -> bool:
        return self.core_ready() and pcsx2.bios_ok(self.game_dir)

    def maybe_shortcut(self, force: bool = False) -> None:
        if os.environ.get("PS2COOP_NO_SHORTCUT", "").lower() in {"1", "true", "yes"}:
            return
        title = self.title()
        still_there = desktop.existing(self.game_dir, title)
        if (
            not force
            and self.profile.get("shortcut")
            and self.profile.get("shortcut_title") == title
            and still_there
        ):
            return
        if not force and self._shortcut_error and self._shortcut_error_title == title:
            return
        old_title = str(self.profile.get("shortcut_title") or "")
        try:
            desktop.create(self.game_dir, title)
            if old_title and old_title != title:
                desktop.remove(old_title)
            with self.lock:
                self.profile["shortcut"] = True
                self.profile["shortcut_title"] = title
                self.save()
            self._shortcut_error = ""
        except Exception as exc:  # noqa: BLE001 - atalho é conveniência
            self._shortcut_error = str(exc)
            self._shortcut_error_title = title

    # -- preparação automática -----------------------------------------
    def _setup_signature(self) -> tuple[Any, ...]:
        image = self.image()
        return (
            image.name if image else "",
            pcsx2.installed(),
            moonlight.installed(),
            moonlight.can_host(),
            pcsx2.bios_ok(self.game_dir),
        )

    def maybe_auto_setup(self) -> None:
        if not self.auto_setup_enabled or not self.image() or pcsx2.running(self.game_dir):
            return
        if self.profile.get("auto_setup_completed") and self.ready():
            self.maybe_shortcut()
            return
        job = self.jobs.get("setup")
        if job and job.running:
            return
        signature = self._setup_signature()
        if job and job.status in ("blocked", "error") and signature == self._auto_last_sig:
            return
        self._auto_last_sig = signature
        self.start_auto_setup(force=True)

    def start_auto_setup(self, force: bool = False) -> Job | None:
        if not self.auto_setup_enabled and not force:
            return None
        current = self.jobs.get("setup")
        if current and current.running:
            return current
        self._auto_last_sig = self._setup_signature()
        return self.jobs.start("setup", "Preparação automática", self._auto_setup_job)

    def _mirror_job(
        self,
        parent: Job,
        job_id: str,
        label: str,
        fn: Any,
        start: float,
        end: float,
    ) -> None:
        child = self.jobs.start(job_id, label, fn)
        while child.running:
            if child.message:
                parent.message = child.message
            if child.progress >= 0:
                parent.progress = start + (end - start) * min(1.0, child.progress)
            time.sleep(0.25)
        if child.status == "error":
            raise RuntimeError(child.error or f"{label} falhou.")
        parent.progress = end
        if child.message:
            parent.message = child.message

    def _auto_setup_job(self, job: Job) -> None:
        image = self.image()
        if not image:
            job.status = "blocked"
            job.progress = 0.0
            job.message = "Coloque um arquivo .iso, .chd ou .cso nesta pasta."
            return

        if not pcsx2.installed():
            job.message = "Baixando o PCSX2…"
            self._mirror_job(job, "pcsx2", "Instalar PCSX2", pcsx2.install, 0.02, 0.45)
        else:
            job.progress = 0.4
            job.message = "PCSX2 pronto"

        if not (moonlight.installed() and moonlight.can_host()):
            job.message = "Instalando o MoonlightWeb…"
            self._mirror_job(job, "moonlight", "Instalar MoonlightWeb", moonlight.install, 0.45, 0.8)
        else:
            job.progress = 0.75
            job.message = "MoonlightWeb pronto"

        if not pcsx2.bios_ok(self.game_dir):
            job.message = "Procurando uma BIOS já instalada…"
            adopted = pcsx2.find_and_adopt_bios(self.game_dir)
            if not adopted:
                job.status = "blocked"
                job.progress = 0.82
                job.message = (
                    "Falta a BIOS do PS2. Envie o arquivo .bin da BIOS do seu console "
                    "na etapa “BIOS do PS2”."
                )
                return
        job.progress = 0.86
        job.message = "Configurando o PCSX2…"
        pads = gamepads.detect_gamepads()
        mapping = gamepads.build_pad_map(self.players(), self.host_local(), pads)
        pcsx2.configure(self.game_dir, self.players(), mapping)

        job.progress = 0.94
        job.message = "Criando o ícone na área de trabalho…"
        self.maybe_shortcut(force=True)

        job.progress = 1.0
        job.message = "Tudo pronto!"
        with self.lock:
            self.profile["auto_setup_completed"] = True
            self.save()

    # -- configuração ---------------------------------------------------
    def bios_summary(self) -> dict[str, Any]:
        ok = pcsx2.bios_ok(self.game_dir)
        return {
            "ok": ok,
            "name": pcsx2.bios_name(self.game_dir) if ok else "",
            "candidates": [str(path) for path in pcsx2.bios_candidates()],
        }

    def setup_status(self) -> dict[str, Any]:
        image = self.image()
        auto_job = self.jobs.get("setup")
        pcsx2_job = self.jobs.get("pcsx2")
        moon_job = self.jobs.get("moonlight")
        bios = self.bios_summary()
        shortcut_ok = desktop.existing(self.game_dir, self.title())
        return {
            "ready": self.ready(),
            "core_ready": self.core_ready(),
            "auto_enabled": self.auto_setup_enabled,
            "auto": auto_job.to_json() if auto_job else None,
            "pcsx2": {
                "installed": pcsx2.installed(),
                "version": pcsx2.version() if pcsx2.installed() else "",
                "path": str(pcsx2.find_executable() or ""),
                "job": pcsx2_job.to_json() if pcsx2_job else None,
            },
            "moonlight": {
                "installed": moonlight.installed(),
                "running": moonlight.running(),
                "can_host": moonlight.can_host(),
                "path": str(moonlight.find() or ""),
                "version": (moonlight.server_probe() or {}).get("version", "") if moonlight.running() else "",
                "job": moon_job.to_json() if moon_job else None,
            },
            "bios": bios,
            "shortcut": {
                "ok": shortcut_ok,
                "title": self.title(),
                "error": self._shortcut_error,
            },
            "image": {
                "ok": image is not None,
                "name": image.name if image else "",
                "title": image.title if image else "",
                "size": image.size if image else 0,
                "human_size": human_size(image.size) if image else "",
                "images": [item.to_json() for item in self.images()],
            },
            "python": platform.python_version(),
            "platform": platform_name(),
        }

    # -- status ---------------------------------------------------------
    def status(self) -> dict[str, Any]:
        # Se a ISO foi copiada com o portal já aberto, sincroniza o perfil e a
        # preparação começa sozinha. A assinatura evita repetir erro a cada poll.
        if self._ensure_image():
            self.save()
        self.maybe_auto_setup()
        self.maybe_shortcut()
        image = self.image()
        pads = gamepads.detect_gamepads()
        virtual, physical, virtual_names, physical_names = gamepads.count_gamepads(pads)
        mapping = gamepads.build_pad_map(self.players(), self.host_local(), pads)
        pad_description = gamepads.pad_map_description(
            self.players(), self.host_local(), pads, mapping
        )

        running = moonlight.running()
        try:
            invites = (
                moonlight.get_invites(
                    False,
                    count=self.remote_players(),
                    first_player=self.first_remote_player(),
                )
                if running
                else []
            )
        except Exception:
            invites = []
        connected_guests = sum(1 for invite in invites if invite.get("connected"))

        try:
            connection = moonlight.connection_info()
        except Exception:
            connection = {
                "lan": "",
                "public": "",
                "public_enabled": False,
                "public_ip": "",
                "running": False,
            }
        try:
            backups = saves.list_backups(self.game_dir)
        except Exception:
            backups = []

        setup = self.setup_status()
        problems: list[str] = []
        if image is None:
            problems.append("Coloque um arquivo .iso, .chd ou .cso nesta pasta.")
        if not setup["pcsx2"]["installed"]:
            problems.append("PCSX2 não instalado.")
        if not setup["moonlight"]["installed"]:
            problems.append("MoonlightWeb não instalado.")
        elif not setup["moonlight"]["can_host"]:
            problems.append(
                "O MoonlightWeb portátil (AppImage) não captura a tela local. Instale o pacote do sistema."
            )
        if not setup["bios"]["ok"]:
            problems.append("BIOS do PS2 não configurada.")
        if setup["auto"] and setup["auto"].get("status") == "error":
            problems.append(setup["auto"].get("error") or "A preparação automática falhou.")

        controls_ready = (not self.host_local() or physical >= 1) and (
            os.name == "nt" or virtual >= self.required_virtual()
        )
        can_start = (
            self.ready()
            and not pcsx2.running(self.game_dir)
            and controls_ready
            and (
                self.remote_players() == 0
                or (
                    running
                    and connected_guests >= self.remote_players()
                )
            )
        )

        return {
            "ok": True,
            "app": {
                "name": APP_NAME,
                "version": VERSION,
                "os": platform_label(),
                "platform": platform_name(),
                "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "logs": str(logs_root()),
            },
            "game": {
                "dir": str(self.game_dir),
                "title": self.title(),
                "image": image.name if image else "",
                "image_title": image.title if image else "",
                "images": [item.to_json() for item in self.images()],
                "players": self.players(),
                "host_local": self.host_local(),
                "invite_network": self.invite_network(),
            },
            "setup": setup,
            "session": {
                "remote_players": self.remote_players(),
                "required_virtual": self.required_virtual(),
                "connected_guests": connected_guests,
                "controls_ready": controls_ready,
                "can_start": can_start,
            },
            "emulation": {
                "running": pcsx2.running(self.game_dir),
                "gamepads": {
                    "virtual": virtual,
                    "physical": physical,
                    "virtual_names": virtual_names,
                    "physical_names": physical_names,
                    "required": self.required_virtual(),
                    "map": pad_description,
                },
            },
            "invites": invites,
            "connection": connection,
            "saves": {
                "dir": str(saves.saves_dir(self.game_dir)),
                "backups": backups,
            },
            "jobs": self.jobs.all(),
            "problems": problems,
        }

    # -- sessão ---------------------------------------------------------
    def create_invites(self, link_address: str | None = None) -> list[dict[str, Any]]:
        if self.remote_players() == 0:
            return []
        if not moonlight.installed():
            raise RuntimeError("Instale o MoonlightWeb primeiro.")
        if not moonlight.can_host():
            raise RuntimeError(
                "O MoonlightWeb portátil (AppImage) não captura a tela local. "
                "Instale o pacote .deb/.rpm do sistema."
            )
        if not moonlight.running():
            moonlight.start()
        network = link_address if link_address in ("auto", "lan") else self.invite_network()
        invites = moonlight.get_invites(
            True,
            network,
            count=self.remote_players(),
            first_player=self.first_remote_player(),
        )
        self.profile["invite_network"] = network
        self.save()
        return invites

    def start_game(self, force: bool = False) -> dict[str, Any]:
        setup_job = self.jobs.get("setup")
        if setup_job and setup_job.running:
            raise RuntimeError("Aguarde a preparação automática terminar antes de iniciar o jogo.")
        image = self.image()
        if not image:
            raise RuntimeError("Nenhuma imagem de PS2 nesta pasta.")
        if not pcsx2.installed():
            raise RuntimeError("Instale o PCSX2 primeiro.")
        if not pcsx2.bios_ok(self.game_dir):
            raise RuntimeError("Configure a BIOS do PS2 primeiro.")
        if pcsx2.running(self.game_dir):
            raise RuntimeError("O jogo já está rodando.")

        remote_needed = self.remote_players()
        invites: list[dict[str, Any]] = []
        running = moonlight.running()
        if remote_needed:
            if not running:
                raise RuntimeError(
                    "Gere os convites e peça para os amigos entrarem antes de iniciar o jogo."
                )
            moonlight.clear_cache()
            invites = moonlight.get_invites(
                False,
                count=remote_needed,
                first_player=self.first_remote_player(),
            )
            connected = sum(1 for invite in invites if invite.get("connected"))
            if connected < remote_needed and not force:
                missing = remote_needed - connected
                people = "convidado" if missing == 1 else "convidados"
                linked = "conectado" if missing == 1 else "conectados"
                raise RuntimeError(
                    f"Faltam {missing} {people} {linked}. "
                    "Peça para cada amigo abrir o link, digitar o PIN e apertar um botão no controle."
                )

        pads = gamepads.detect_gamepads(force=True)
        mapping = gamepads.build_pad_map(self.players(), self.host_local(), pads)
        virtual, physical, _, _ = gamepads.count_gamepads(pads)
        if not force:
            if self.host_local() and physical < 1:
                raise RuntimeError(
                    "Modo host local: conecte um controle físico no PC ou marque “iniciar mesmo assim”."
                )
            if not self.host_local() and virtual < self.players() and os.name != "nt":
                missing = self.players() - virtual
                word = "controle virtual" if missing == 1 else "controles virtuais"
                raise RuntimeError(
                    f"Faltam {missing} {word}: {virtual}/{self.players()}. "
                    "Peça para cada amigo entrar e apertar um botão no controle."
                )
            if self.host_local() and virtual < self.required_virtual() and os.name != "nt":
                missing = self.required_virtual() - virtual
                word = "controle virtual" if missing == 1 else "controles virtuais"
                raise RuntimeError(
                    f"Faltam {missing} {word}: {virtual}/{self.required_virtual()}. "
                    "Peça para cada amigo entrar e apertar um botão no controle."
                )

        pid = pcsx2.start(
            self.game_dir,
            image.path,
            self.players(),
            fullscreen=True,
            pad_map=mapping,
        )
        self.maybe_shortcut()
        return {"pid": pid, "players": self.players(), "pad_map": mapping}

    def stop_game(self) -> dict[str, Any]:
        pcsx2.stop(self.game_dir)
        backup = None
        try:
            backup = saves.backup(self.game_dir)
        except Exception:
            backup = None
        return {"backup": backup}

    def after_bios(self) -> None:
        self.maybe_shortcut(force=True)
        if self.auto_setup_enabled:
            self.start_auto_setup(force=True)


class PortalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        # Numa build --windowed do Windows sys.stderr é None; não deixe um erro
        # de socket virar outro erro ao tentar imprimir o traceback.
        try:
            if sys.stderr:
                super().handle_error(request, client_address)
        except Exception:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = "PS2Coop/1.0"
    state: AppState

    # -- infraestrutura -------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:
        try:
            if getattr(self, "path", "").startswith("/api/status"):
                return
            if sys.stderr:
                sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))
                sys.stderr.flush()
        except Exception:
            pass

    def _host_ok(self) -> bool:
        host = self.headers.get("Host", "")
        if not host:
            return False
        if host.startswith("["):
            name = host[1 : host.find("]")] if "]" in host else host
        else:
            name = host.rsplit(":", 1)[0] if ":" in host else host
        return name.lower() in {"127.0.0.1", "localhost", "::1"}

    def _cross_site(self) -> bool:
        site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        return site == "cross-site"

    def _guard(self, mutation: bool) -> bool:
        if not self._host_ok():
            self._json({"ok": False, "error": "Host não permitido."}, 403)
            return False
        if self._cross_site():
            self._json({"ok": False, "error": "Requisição bloqueada."}, 403)
            return False
        if mutation:
            origin = (self.headers.get("Origin") or "").strip()
            if origin:
                parsed = urlparse(origin)
                origin_host = parsed.netloc
                if origin_host.lower() != self.headers.get("Host", "").lower():
                    self._json({"ok": False, "error": "Origem não permitida."}, 403)
                    return False
            token = self.headers.get("X-PS2Coop-Token", "")
            if not token or not secrets.compare_digest(token, self.state.token):
                self._json({"ok": False, "error": "Token de sessão inválido. Recarregue a página."}, 403)
                return False
        return True

    def _json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            if length > 1024 * 1024:
                raise ValueError("Corpo grande demais.")
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Corpo inválido: {exc}") from exc

    def _static(self, path: str) -> None:
        web = (resource_root() / "web").resolve()
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (web / rel).resolve()
        if target != web and web not in target.parents:
            self.send_error(403)
            return
        if not target.is_file():
            self.send_error(404)
            return

        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.name == "index.html":
            raw = target.read_text(encoding="utf-8").replace("__PS2COOP_TOKEN__", self.state.token)
            body = raw.encode("utf-8")
            ctype = "text/html; charset=utf-8"
        else:
            body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    # -- rotas ----------------------------------------------------------
    def do_GET(self) -> None:
        if not self._guard(mutation=False):
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            try:
                self._json(self.state.status())
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 500)
            return
        if parsed.path == "/api/setup/bios/candidates":
            self._json({"ok": True, "candidates": [str(path) for path in pcsx2.bios_candidates()]})
            return
        self._static(parsed.path)

    def do_POST(self) -> None:
        if not self._guard(mutation=True):
            return
        parsed = urlparse(self.path)
        route = parsed.path
        state = self.state
        try:
            if route == "/api/game/select":
                if pcsx2.running(state.game_dir):
                    raise RuntimeError("Pare o jogo antes de trocar a ISO.")
                body = self._body()
                name = str(body.get("image") or "")
                image = find_image_by_name(state.game_dir, name)
                if not image:
                    raise RuntimeError("Imagem não encontrada.")
                state.profile["image"] = image.name
                state.profile["title"] = image.title
                state.profile["shortcut"] = False
                state.save()
                state.maybe_shortcut(force=True)
                state.maybe_auto_setup()
                self._json({"ok": True, "image": image.to_json()})
                return

            if route == "/api/game/players":
                body = self._body()
                players = max(1, min(4, int(body.get("players") or 2)))
                host_local = (
                    bool(state.profile.get("host_local"))
                    if "host_local" not in body
                    else bool(body.get("host_local"))
                )
                result = state.set_players(players, host_local)
                self._json({"ok": True, **result})
                return

            if route == "/api/settings":
                body = self._body()
                network = str(body.get("invite_network") or "")
                if network in ("auto", "lan"):
                    state.profile["invite_network"] = network
                    state.save()
                self._json({"ok": True, "invite_network": state.invite_network()})
                return

            if route == "/api/setup/auto":
                if pcsx2.running(state.game_dir):
                    raise RuntimeError("Pare o jogo antes de preparar o ambiente.")
                job = state.start_auto_setup(force=True)
                if not job:
                    raise RuntimeError("A preparação automática está desativada.")
                self._json({"ok": True, "job": job.to_json()})
                return

            if route in ("/api/setup/pcsx2", "/api/setup/moonlight"):
                if pcsx2.running(state.game_dir):
                    raise RuntimeError("Pare o jogo antes de instalar componentes.")
                setup = state.jobs.get("setup")
                if setup and setup.running:
                    raise RuntimeError("A preparação automática já está em andamento.")
                if route.endswith("pcsx2"):
                    job = state.jobs.start("pcsx2", "Instalar PCSX2", pcsx2.install)
                else:
                    job = state.jobs.start("moonlight", "Instalar MoonlightWeb", moonlight.install)
                self._json({"ok": True, "job": job.to_json()})
                return

            if route == "/api/setup/bios":
                if pcsx2.running(state.game_dir):
                    raise RuntimeError("Pare o jogo antes de trocar a BIOS.")
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_BIOS_SIZE:
                    raise RuntimeError("Envie um arquivo de BIOS de até 8 MB.")
                raw = self.rfile.read(length)
                filename = self.headers.get("X-Filename") or parse_qs(parsed.query).get("name", ["bios.bin"])[0]
                name = pcsx2.save_bios_file(state.game_dir, filename, raw)
                state.after_bios()
                self._json({"ok": True, "name": name})
                return

            if route == "/api/setup/bios/adopt":
                if pcsx2.running(state.game_dir):
                    raise RuntimeError("Pare o jogo antes de trocar a BIOS.")
                body = self._body()
                source = Path(str(body.get("path") or "")).expanduser()
                if not source.exists():
                    raise RuntimeError("Pasta de BIOS não encontrada.")
                ini: Path | None = None
                if source.is_file():
                    ini = source
                    source = source.parent
                if source.name == "bios":
                    candidate = source.parent / "inis" / "PCSX2.ini"
                    if candidate.is_file():
                        ini = candidate
                name = pcsx2.adopt_bios(state.game_dir, source, ini)
                state.after_bios()
                self._json({"ok": True, "name": name})
                return

            if route == "/api/setup/shortcut":
                result = desktop.create(state.game_dir, state.title())
                state.profile["shortcut"] = True
                state.profile["shortcut_title"] = state.title()
                state._shortcut_error = ""
                state.save()
                self._json(result)
                return

            if route == "/api/start":
                body = self._body()
                result = state.start_game(force=bool(body.get("force")))
                self._json({"ok": True, **result})
                return

            if route == "/api/stop":
                self._json({"ok": True, **state.stop_game()})
                return

            if route == "/api/invites/create":
                body = self._body()
                self._json(
                    {
                        "ok": True,
                        "invites": state.create_invites(str(body.get("link_address") or "")),
                    }
                )
                return

            if route == "/api/invites/revoke":
                self._json(moonlight.revoke_invites())
                return

            if route == "/api/saves/backup":
                self._json(saves.backup(state.game_dir))
                return

            if route == "/api/saves/restore":
                body = self._body()
                self._json(saves.restore(state.game_dir, str(body.get("name") or "")))
                return

            if route == "/api/open/host":
                if not moonlight.running():
                    moonlight.start()
                moonlight.open_host()
                self._json({"ok": True})
                return

            if route == "/api/open/admin":
                if not moonlight.running():
                    moonlight.start()
                moonlight.open_admin()
                self._json({"ok": True})
                return

            if route == "/api/open/saves":
                saves.open_folder(state.game_dir)
                self._json({"ok": True})
                return

            if route == "/api/open/folder":
                open_in_file_manager(state.game_dir)
                self._json({"ok": True})
                return

            if route == "/api/open/logs":
                open_in_file_manager(logs_root())
                self._json({"ok": True})
                return

            if route == "/api/open/pcsx2logs":
                open_in_file_manager(profile_root(state.game_dir) / "logs")
                self._json({"ok": True})
                return

            if route == "/api/moonlight/start":
                moonlight.start()
                self._json({"ok": True})
                return

            if route == "/api/quit":
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

            self._json({"ok": False, "error": "Rota desconhecida"}, 404)
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": str(exc)}, 400)


def _portal_file(game_dir: Path) -> Path:
    return profile_root(game_dir) / "portal.json"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                text=True,
                capture_output=True,
                timeout=5,
                stdin=subprocess.DEVNULL,
                creationflags=0x08000000,
            )
            fields = (result.stdout or "").split()
            return len(fields) >= 2 and fields[1] == str(pid)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _existing_port(game_dir: Path) -> int | None:
    data = read_json(_portal_file(game_dir))
    try:
        pid = int(data.get("pid") or 0)
        port = int(data.get("port") or 0)
    except (TypeError, ValueError):
        return None
    if not pid or not port or not _pid_alive(pid):
        return None
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.6):
            pass
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=6) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        if isinstance(data, dict) and data.get("app", {}).get("name") == APP_NAME:
            return port
    except Exception:
        return None
    return None


def run(
    game_dir: Path,
    port: int = 8090,
    open_browser: bool = True,
    auto_setup: bool = True,
) -> None:
    existing = _existing_port(game_dir)
    if existing:
        url = f"http://127.0.0.1:{existing}/"
        _console(f"{APP_NAME} já está rodando em {url}")
        if open_browser:
            try:
                open_url(url)
            except Exception as exc:  # noqa: BLE001
                _console(f"Abra manualmente no navegador: {url} ({exc})")
        return

    state = AppState(game_dir, auto_setup=auto_setup)
    Handler.state = state

    server: ThreadingHTTPServer | None = None
    for candidate in (port, 0):
        try:
            server = PortalServer(("127.0.0.1", candidate), Handler)
            break
        except OSError:
            continue
    if server is None:
        _fatal("Não foi possível abrir a porta do portal.")

    actual_port = server.server_address[1]
    write_json(
        _portal_file(game_dir),
        {"pid": os.getpid(), "port": actual_port, "game_dir": str(game_dir), "version": VERSION},
    )
    url = f"http://127.0.0.1:{actual_port}/"
    _console(f"{APP_NAME} em {url}")
    _console(f"Jogo: {state.title()} ({game_dir})")

    if state.auto_setup_enabled:
        threading.Timer(1.2, state.maybe_auto_setup).start()
    if open_browser:
        def _open_browser() -> None:
            try:
                if not webbrowser.open(url):
                    raise RuntimeError("nenhum navegador disponível")
            except Exception as exc:  # noqa: BLE001
                _console(f"Abra manualmente no navegador: {url} ({exc})")
                if os.name == "nt":
                    try:
                        import ctypes

                        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
                            None,
                            f"Abra este endereço no navegador:\n{url}",
                            APP_NAME,
                            0x40,
                        )
                    except Exception:
                        pass

        threading.Timer(0.6, _open_browser).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.server_close()
        except Exception:
            pass
        try:
            _portal_file(game_dir).unlink(missing_ok=True)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(value in ("-h", "--help") for value in args):
        print(
            f"{APP_NAME} {VERSION}\n"
            "Uso: app.py [--game PASTA] [--port 8090] [--no-browser] [--no-auto-setup]\n"
        )
        return
    if sys.version_info < (3, 10):
        _fatal("O PS2 Co-op precisa de Python 3.10 ou mais novo.")
    game_dir = game_dir_from_argv(args)
    if not game_dir.is_dir():
        _fatal(f"A pasta do jogo não existe: {game_dir}")
    port = 8090
    open_browser = "--no-browser" not in args
    auto_setup = "--no-auto-setup" not in args
    for index, value in enumerate(args):
        if value == "--port" and index + 1 < len(args):
            try:
                port = int(args[index + 1])
            except ValueError:
                pass
        elif value.startswith("--port="):
            try:
                port = int(value.split("=", 1)[1])
            except ValueError:
                pass
    try:
        run(game_dir, port=port, open_browser=open_browser, auto_setup=auto_setup)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        _fatal(f"Não foi possível iniciar o PS2 Co-op: {exc}")


if __name__ == "__main__":
    main()
