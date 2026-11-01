#!/usr/bin/env python3
"""Gera o executável de um arquivo só com PyInstaller.

Uso:
    python3 -m pip install -r requirements-build.txt
    python3 build.py

O resultado fica em dist/ps2coop (Linux) ou dist/ps2coop.exe (Windows).
Os arquivos web/ e assets/ são embutidos no executável.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    if sys.version_info < (3, 10):
        print("Use Python 3.10 ou mais novo para compilar.")
        return 1
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller não instalado. Rode:")
        print("  python3 -m pip install -r requirements-build.txt")
        return 1

    sep = ";" if os.name == "nt" else ":"
    icon = ROOT / "assets" / ("icon.ico" if os.name == "nt" else "icon.png")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "ps2coop",
        "--add-data",
        f"{ROOT / 'web'}{sep}web",
        "--add-data",
        f"{ROOT / 'assets'}{sep}assets",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
        "--specpath",
        str(ROOT / "build"),
    ]
    if icon.is_file():
        command += ["--icon", str(icon)]
    if os.name == "nt":
        command += ["--windowed"]
    command.append(str(ROOT / "app.py"))
    print(" ".join(command))
    subprocess.run(command, check=True, cwd=ROOT)

    target = ROOT / "dist" / ("ps2coop.exe" if os.name == "nt" else "ps2coop")
    if not target.is_file():
        print("O executável não foi gerado.")
        return 1
    print(f"Pronto: {target} ({target.stat().st_size / 1024 / 1024:.1f} MB)")
    if os.name != "nt":
        target.chmod(0o755)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
