#!/usr/bin/env bash
# Inicia o PS2 Co-op na pasta em que este arquivo está.
set -euo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
GAME_DIR="${PS2COOP_GAME_DIR:-$APP_DIR}"

if [ -x "$APP_DIR/ps2coop-bin" ] && [ "${PS2COOP_FROM_SOURCE:-0}" != "1" ]; then
    if "$APP_DIR/ps2coop-bin" "$@" --game "$GAME_DIR"; then
        exit 0
    fi
    echo "O binário não iniciou; tentando pelo código-fonte..." >&2
fi

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
            PY="$candidate"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    MESSAGE="O PS2 Co-op precisa de Python 3.10 ou mais novo.
No Ubuntu/Debian: sudo apt install python3
No Fedora: sudo dnf install python3
No Arch: sudo pacman -S python"
    echo "$MESSAGE" >&2
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --title="PS2 Co-op" --text="$MESSAGE" 2>/dev/null || true
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --error "$MESSAGE" 2>/dev/null || true
    fi
    exit 1
fi

if [ ! -f "$APP_DIR/app.py" ]; then
    echo "app.py não encontrado em $APP_DIR." >&2
    exit 1
fi

exec "$PY" "$APP_DIR/app.py" "$@" --game "$GAME_DIR"
