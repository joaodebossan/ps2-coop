#!/usr/bin/env python3
"""Cria os pacotes de distribuição em dist/.

- PS2Coop-Windows.zip: fonte + iniciar.bat (baixa Python portátil e os componentes)
- PS2Coop-Linux.tar.gz: fonte + iniciar.sh (e o binário ps2coop, se já compilado)
"""

from __future__ import annotations

import os
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

COMMON = [
    "app.py",
    "iniciar.sh",
    "iniciar.bat",
    "README.md",
    "LICENSE",
    "ps2coop",
    "web",
    "assets",
    "tools",
    "requirements-build.txt",
    "Makefile",
]


def files() -> list[Path]:
    result: list[Path] = []
    for name in COMMON:
        path = ROOT / name
        if path.is_file():
            result.append(path)
        elif path.is_dir():
            for entry in path.rglob("*"):
                if entry.is_file() and "__pycache__" not in entry.parts:
                    result.append(entry)
    return result


def add_to_zip(bundle: zipfile.ZipFile, path: Path) -> None:
    bundle.write(path, path.relative_to(ROOT).as_posix())


def add_to_tar(bundle: tarfile.TarFile, path: Path, arcname: str | None = None) -> None:
    info = bundle.gettarinfo(str(path), arcname or path.relative_to(ROOT).as_posix())
    if path.name in ("iniciar.sh", "ps2coop", "ps2coop-bin") or arcname == "ps2coop-bin":
        info.mode |= 0o755
    with path.open("rb") as handle:
        bundle.addfile(info, handle)


def main() -> None:
    DIST.mkdir(exist_ok=True)
    source_files = files()

    win_zip = DIST / "PS2Coop-Windows.zip"
    with zipfile.ZipFile(win_zip, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in source_files:
            add_to_zip(bundle, path)
        exe = next(
            (candidate for candidate in (DIST / "PS2Coop.exe", DIST / "ps2coop.exe") if candidate.is_file()),
            None,
        )
        if exe:
            bundle.write(exe, "PS2Coop.exe")

    linux_tar = DIST / "PS2Coop-Linux.tar.gz"
    with tarfile.open(linux_tar, "w:gz") as bundle:
        for path in source_files:
            add_to_tar(bundle, path)
        binary = DIST / "ps2coop"
        if binary.is_file():
            # "ps2coop" já é o pacote Python dentro do tar; o binário precisa
            # de outro nome para não virar uma pasta.
            add_to_tar(bundle, binary, "ps2coop-bin")

    for path in (win_zip, linux_tar):
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
