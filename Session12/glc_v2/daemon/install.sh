#!/usr/bin/env bash
# Cross-platform installer for glc_v1 as a per-user daemon.
# Detects macOS / Linux / Windows-WSL and drops the right service file.
#
# Usage:
#   ./daemon/install.sh                # install + start
#   ./daemon/install.sh --uninstall    # stop + remove
#   ./daemon/install.sh --models       # download Kokoro + whisper.cpp base model
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

UV_BIN="$(command -v uv || true)"
if [[ -z "${UV_BIN}" ]]; then
    echo "uv is not on PATH. Install it from https://docs.astral.sh/uv/ and retry."
    exit 1
fi

substitute() {
    sed \
        -e "s#{{GLC_HOME}}#${ROOT}#g" \
        -e "s#{{UV_BIN}}#${UV_BIN}#g" \
        -e "s#{{HOME}}#${HOME}#g" \
        -e "s#{{APPDATA}}#${APPDATA:-${HOME}/AppData/Roaming}#g" \
        "$1"
}

UNAME="$(uname -s)"
ACTION="${1:-install}"

case "$ACTION" in
    --models)
        echo "==> downloading Kokoro-82M and whisper.cpp base model"
        mkdir -p "${HOME}/.glc/models"
        echo "    (Kokoro: install via 'uv pip install kokoro' then it lazy-loads.)"
        echo "    (whisper.cpp: build whisper-cli from source and drop ggml-base.bin into ~/.glc/models/whisper-base/)"
        exit 0
        ;;
    --uninstall)
        case "$UNAME" in
            Darwin)
                launchctl unload -w "${HOME}/Library/LaunchAgents/com.thinkers.glc.plist" 2>/dev/null || true
                rm -f "${HOME}/Library/LaunchAgents/com.thinkers.glc.plist"
                ;;
            Linux)
                systemctl --user disable --now glc.service 2>/dev/null || true
                rm -f "${HOME}/.config/systemd/user/glc.service"
                systemctl --user daemon-reload 2>/dev/null || true
                ;;
            *)
                echo "Windows: 'nssm remove GLC confirm' to uninstall."
                ;;
        esac
        echo "uninstalled."
        exit 0
        ;;
esac

(cd "$ROOT" && uv sync)

case "$UNAME" in
    Darwin)
        mkdir -p "${HOME}/Library/LaunchAgents" "${HOME}/Library/Logs/glc"
        substitute "${HERE}/launchd.plist.template" > "${HOME}/Library/LaunchAgents/com.thinkers.glc.plist"
        launchctl unload "${HOME}/Library/LaunchAgents/com.thinkers.glc.plist" 2>/dev/null || true
        launchctl load -w "${HOME}/Library/LaunchAgents/com.thinkers.glc.plist"
        echo "installed launchd agent: com.thinkers.glc"
        ;;
    Linux)
        mkdir -p "${HOME}/.config/systemd/user"
        substitute "${HERE}/systemd.service.template" > "${HOME}/.config/systemd/user/glc.service"
        systemctl --user daemon-reload
        systemctl --user enable --now glc.service
        echo "installed systemd user service: glc.service"
        ;;
    *)
        echo "Windows host detected. Install NSSM (https://nssm.cc/) and:"
        substitute "${HERE}/windows-service.xml.template"
        ;;
esac

echo
echo "Gateway will boot on http://localhost:8111"
echo "Per-installation token: $(uv run --directory "$ROOT" glc token)"
