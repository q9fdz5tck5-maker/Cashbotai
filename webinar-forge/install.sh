#!/usr/bin/env bash
# Prepare a fresh server to build webinars.
#
#   ./install.sh            node deps + system packages, skip the ML stack
#   ./install.sh --engine   also build the voice engine venv (installs torch)
#
# Supports Debian/Ubuntu (apt) and macOS (brew). On anything else it prints the
# package list and leaves the system alone.

set -euo pipefail
cd "$(dirname "$0")"

WITH_ENGINE=0
[ "${1:-}" = "--engine" ] && WITH_ENGINE=1

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

PKGS_APT="ffmpeg chromium python3 python3-venv python3-pip curl"
PKGS_BREW="ffmpeg chromium python@3.11"

say "Checking prerequisites"

if have apt-get; then
  SUDO=""
  [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  $SUDO apt-get update -qq
  # chromium is a snap on some Ubuntu releases; fall back to chromium-browser.
  $SUDO apt-get install -y $PKGS_APT || $SUDO apt-get install -y ffmpeg chromium-browser python3 python3-venv python3-pip curl
elif have brew; then
  brew install $PKGS_BREW || true
else
  echo "Unrecognised package manager. Install these yourself, then re-run:"
  echo "  $PKGS_APT"
fi

if ! have node; then
  echo
  echo "Node.js 18+ is required and was not found."
  echo "  Debian/Ubuntu:  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs"
  echo "  macOS:          brew install node"
  exit 1
fi

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 18 ]; then
  echo "Node.js 18+ required (found $(node -v))."
  exit 1
fi

say "Installing Node dependencies"
npm install --omit=dev --no-audit --no-fund

[ -f .env ] || { cp .env.example .env; echo "Created .env from .env.example"; }

if [ "$WITH_ENGINE" -eq 1 ]; then
  say "Building the voice engine venv (this downloads torch — several minutes)"
  python3 -m venv engine/.venv
  ./engine/.venv/bin/pip install --upgrade pip
  ./engine/.venv/bin/pip install -r engine/requirements.txt
else
  say "Skipping the voice engine"
  echo "Run './install.sh --engine' when you are ready to install torch + Chatterbox,"
  echo "or use the mock engine to try the pipeline now:  npm run mock-engine"
fi

say "Verifying"
node bin/webinar-forge doctor || true

cat <<'NEXT'

Next steps
  1. Add a voice sample:   node bin/webinar-forge add-voice my-voice sample.wav
  2. Create a project:     node bin/webinar-forge init projects/my-webinar
  3. Build it:             node bin/webinar-forge build projects/my-webinar/project.json

NEXT
