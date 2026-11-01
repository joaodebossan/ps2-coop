#!/usr/bin/env bash
# Empacota o binário PyInstaller (dist/ps2coop) num único .AppImage.
# Uso: ./tools/build_appimage.sh [caminho-do-binário] [saída.AppImage]
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${1:-$ROOT/dist/ps2coop}"
OUT="${2:-$ROOT/dist/PS2Coop-x86_64.AppImage}"
APPDIR="$ROOT/build/appimage/PS2Coop.AppDir"
TOOL="$ROOT/build/appimagetool-x86_64.AppImage"

if [ ! -x "$BIN" ]; then
    echo "Binário não encontrado/executável: $BIN" >&2
    echo "Rode primeiro: python3 build.py" >&2
    exit 1
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/doc/ps2coop"
cp "$BIN" "$APPDIR/usr/bin/ps2coop"
chmod 755 "$APPDIR/usr/bin/ps2coop"
cp "$ROOT/assets/icon-256.png" "$APPDIR/ps2coop.png"
cp "$ROOT/LICENSE" "$APPDIR/usr/share/doc/ps2coop/LICENSE"
ln -s ps2coop.png "$APPDIR/.DirIcon"

cat > "$APPDIR/ps2coop.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=PS2 Co-op
Comment=Servidor local de co-op PS2
Exec=ps2coop
Icon=ps2coop
Terminal=false
Categories=Game;Emulator;
StartupNotify=false
DESKTOP

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
# O app detecta o APPIMAGE e usa a pasta onde o .AppImage está como pasta do jogo.
here="$(dirname "$(readlink -f "$0")")"
exec "$here/usr/bin/ps2coop" "$@"
APPRUN
chmod 755 "$APPDIR/AppRun" "$APPDIR/ps2coop.desktop"

if ! command -v appimagetool >/dev/null 2>&1 && [ ! -x "$TOOL" ]; then
    mkdir -p "$(dirname "$TOOL")"
    echo "Baixando appimagetool…"
    curl -L --fail --retry 3 --connect-timeout 20 \
        -o "$TOOL" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod 755 "$TOOL"
fi

if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="$(command -v appimagetool)"
else
    APPIMAGETOOL="$TOOL"
fi

mkdir -p "$(dirname "$OUT")"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" --no-appstream "$APPDIR" "$OUT"
chmod 755 "$OUT"
echo "Pronto: $OUT ($(du -h "$OUT" | cut -f1))"
