"""Downloads resilientes, jobs em background e utilidades de arquivo."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

USER_AGENT = "PS2Co-op/1.0 (+local desktop app)"
GITHUB_API = "https://api.github.com"
_GITHUB_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}
_GITHUB_LOCK = threading.Lock()


@dataclass
class Job:
    id: str
    label: str
    status: str = "pending"  # pending | running | done | error | blocked
    progress: float = 0.0  # 0..1, -1 = indeterminado
    message: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    @property
    def running(self) -> bool:
        return self.status in ("pending", "running")

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "progress": self.progress if self.progress >= 0 else None,
            "message": self.message,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {key: job.to_json() for key, job in self._jobs.items()}

    def start(self, job_id: str, label: str, fn: Callable[[Job], Any]) -> Job:
        with self._lock:
            existing = self._jobs.get(job_id)
            if existing and existing.running:
                return existing
            job = Job(id=job_id, label=label, status="running")
            self._jobs[job_id] = job

        def run() -> None:
            try:
                fn(job)
                if job.status == "running":
                    job.status = "done"
                    job.progress = 1.0
            except Exception as exc:  # noqa: BLE001 - vira erro visível na UI
                job.status = "error"
                job.error = str(exc)
                job.message = "Falhou"
            finally:
                job.finished_at = time.time()

        threading.Thread(target=run, name=f"job-{job_id}", daemon=True).start()
        return job


def describe_bytes(value: float) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value:.0f} B"


def _open_url(url: str, headers: dict[str, str] | None = None, timeout: int = 60):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(request, timeout=timeout)


def _download_once(
    url: str,
    dest: Path,
    job: Job | None,
    timeout: int,
    resume: bool,
) -> None:
    part = dest.with_name(dest.name + ".part")
    existing = part.stat().st_size if resume and part.is_file() else 0
    headers: dict[str, str] = {}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    if job:
        job.message = "Conectando…"
        job.progress = -1

    with _open_url(url, headers, timeout) as response:
        status = getattr(response, "status", 200)
        if existing and status != 206:
            # O servidor ignorou o Range: começa de novo.
            existing = 0
            part.unlink(missing_ok=True)
        total_header = response.headers.get("Content-Length")
        total = int(total_header or 0) + existing
        mode = "ab" if existing else "wb"
        downloaded = existing
        with part.open(mode) as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if job:
                    job.progress = downloaded / total if total else -1
                    job.message = (
                        f"{describe_bytes(downloaded)} de {describe_bytes(total)}"
                        if total
                        else f"{describe_bytes(downloaded)} baixados"
                    )
    part.replace(dest)
    if job:
        job.progress = 1.0
        job.message = "Download concluído"


def download(
    url: str,
    dest: Path,
    job: Job | None = None,
    timeout: int = 60,
    attempts: int = 3,
    resume: bool = True,
    expected_sha256: str = "",
) -> Path:
    """Baixa para um .part, tenta de novo e valida SHA-256 quando informado."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            _download_once(url, dest, job, timeout, resume and attempt > 0)
            if expected_sha256:
                actual = sha256(dest)
                if actual.lower() != expected_sha256.lower():
                    dest.unlink(missing_ok=True)
                    raise RuntimeError(
                        "O arquivo baixado não confere com o checksum esperado. "
                        "Tente novamente ou baixe manualmente."
                    )
            return dest
        except Exception as exc:  # noqa: BLE001 - retry de rede
            last_error = exc
            if job and attempt < attempts:
                job.message = f"Falhou; tentando de novo ({attempt + 1}/{attempts})…"
                job.progress = -1
                time.sleep(min(2 * attempt, 5))
    try:
        part.unlink(missing_ok=True)
    except OSError:
        pass
    raise RuntimeError(f"Falha no download: {last_error}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: str) -> bool:
    if not expected:
        return True
    try:
        return path.is_file() and sha256(path).lower() == expected.lower()
    except OSError:
        return False


def extract_zip(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(dest)


def copy_tree(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = dest / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True)
        elif entry.is_file():
            shutil.copy2(entry, target)


def run_command(
    command: list[str],
    timeout: int | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd) if cwd else None,
        "env": env,
        "text": True,
        "capture_output": True,
        "timeout": timeout,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.run(command, **kwargs)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def executable_on_path(name: str) -> Path | None:
    found = shutil.which(name)
    return Path(found).resolve() if found else None


def is_admin() -> bool:
    if os.name == "nt":
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def github_release(repo: str, timeout: int = 12, max_age: int = 3600) -> dict[str, Any] | None:
    """Metadados da última release, com cache em memória. None se offline."""
    key = repo.lower()
    now = time.time()
    with _GITHUB_LOCK:
        cached = _GITHUB_CACHE.get(key)
        if cached and now - cached[0] < max_age:
            return cached[1]

    data: dict[str, Any] | None = None
    try:
        with _open_url(
            f"{GITHUB_API}/repos/{repo}/releases/latest",
            {"Accept": "application/vnd.github+json"},
            timeout=timeout,
        ) as response:
            parsed = json.loads(response.read().decode("utf-8", errors="replace"))
        if isinstance(parsed, dict):
            data = parsed
    except Exception:  # noqa: BLE001 - offline/rate limit: usa fallback fixo
        data = None

    with _GITHUB_LOCK:
        _GITHUB_CACHE[key] = (now, data)
    return data


def release_asset(release: dict[str, Any] | None, predicate: Callable[[str], bool]) -> dict[str, Any] | None:
    if not release:
        return None
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        if predicate(name):
            return asset
    return None


def asset_digest(asset: dict[str, Any] | None) -> str:
    if not asset:
        return ""
    digest = str(asset.get("digest") or "")
    if digest.startswith("sha256:"):
        return digest.split(":", 1)[1]
    return ""


def asset_url(asset: dict[str, Any] | None, fallback: str) -> str:
    if asset and asset.get("browser_download_url"):
        return str(asset["browser_download_url"])
    return fallback
