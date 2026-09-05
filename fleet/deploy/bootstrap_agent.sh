#!/usr/bin/env bash
# Turn a bare VPS (or any Linux box on your own network) into a fleet worker.
#
#   sudo bash bootstrap_agent.sh --hub https://hub.example.com \
#       --enroll-token <token> --name video-01 --roles video --slots 2
#
# Installs the agent, its dependencies for the roles you asked for, and a
# systemd unit that restarts it on boot. Safe to re-run: it updates in place.
set -euo pipefail

HUB="" ENROLL_TOKEN="" NAME="$(hostname)" ROLES="general" SLOTS=1
ALLOW_SHELL="" INSTALL_DIR="/opt/fleet" WITH_TTS="" WITH_VIDEO="" INSECURE=""

usage() {
    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
    cat <<'EOF'

Options:
  --hub URL              hub base URL (required)
  --enroll-token TOKEN   one-time enrollment token (required)
  --name NAME            server name in the fleet (default: hostname)
  --roles LIST           comma separated: audio,video,webinar,general
  --slots N              concurrent jobs this box runs (default: 1)
  --allow-shell          permit remote shell jobs on this box
  --insecure             skip TLS verification (self-signed hub on a LAN)
  --install-dir DIR      default /opt/fleet
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hub) HUB="$2"; shift 2 ;;
        --enroll-token) ENROLL_TOKEN="$2"; shift 2 ;;
        --name) NAME="$2"; shift 2 ;;
        --roles) ROLES="$2"; shift 2 ;;
        --slots) SLOTS="$2"; shift 2 ;;
        --allow-shell) ALLOW_SHELL="--allow-shell"; shift ;;
        --insecure) INSECURE="--insecure"; shift ;;
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage; exit 2 ;;
    esac
done

[[ -n "$HUB" ]] || { echo "ERROR: --hub is required" >&2; exit 2; }
[[ -n "$ENROLL_TOKEN" ]] || { echo "ERROR: --enroll-token is required" >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo "ERROR: run this with sudo" >&2; exit 2; }

# Only install the heavy packages a box actually needs for its roles.
case ",$ROLES," in *,video,*|*,webinar,*|*,'*',*) WITH_VIDEO=1 ;; esac
case ",$ROLES," in *,audio,*|*,webinar,*|*,'*',*) WITH_TTS=1 ;; esac

echo "==> Installing fleet agent"
echo "    hub:   $HUB"
echo "    name:  $NAME"
echo "    roles: $ROLES (slots: $SLOTS)"

if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 ca-certificates curl >/dev/null
    [[ -n "$WITH_VIDEO" ]] && { echo "==> Installing ffmpeg"; apt-get install -y -qq ffmpeg >/dev/null; }
    [[ -n "$WITH_TTS" ]] && { echo "==> Installing espeak-ng (piper fallback)"; apt-get install -y -qq espeak-ng >/dev/null; }
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q python3 ca-certificates curl
    [[ -n "$WITH_VIDEO" ]] && dnf install -y -q ffmpeg
    [[ -n "$WITH_TTS" ]] && dnf install -y -q espeak-ng
else
    echo "WARNING: unknown package manager. Ensure python3"
    [[ -n "$WITH_VIDEO" ]] && echo "         and ffmpeg"
    echo "         are installed."
fi

id -u fleet >/dev/null 2>&1 || useradd --system --home-dir "$INSTALL_DIR" \
    --shell /usr/sbin/nologin fleet

mkdir -p "$INSTALL_DIR" "$INSTALL_DIR/work" /var/lib/fleet

# The agent source sits next to this script when run from the bundle.
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$SRC_DIR/fleet_agent.py" ]]; then
    echo "==> Copying agent from $SRC_DIR"
    cp -r "$SRC_DIR"/fleet_agent.py "$SRC_DIR"/fleetlib "$SRC_DIR"/handlers \
          "$SRC_DIR"/drivers "$SRC_DIR"/__init__.py "$INSTALL_DIR"/ 2>/dev/null || true
    # fleet_agent.py imports `fleet.handlers`, so it needs a package dir above it.
    mkdir -p "$INSTALL_DIR/fleet"
    cp -r "$SRC_DIR"/handlers "$SRC_DIR"/fleetlib "$SRC_DIR"/drivers \
          "$SRC_DIR"/__init__.py "$INSTALL_DIR/fleet"/ 2>/dev/null || true
else
    echo "ERROR: could not find fleet_agent.py next to this script." >&2
    echo "       Copy the whole fleet/ directory to this machine first." >&2
    exit 1
fi

chown -R fleet:fleet "$INSTALL_DIR" /var/lib/fleet

cat > /etc/systemd/system/fleet-agent.service <<EOF
[Unit]
Description=Cashbot fleet worker agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=fleet
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 $INSTALL_DIR/fleet_agent.py \\
    --hub $HUB \\
    --enroll-token $ENROLL_TOKEN \\
    --name $NAME \\
    --roles $ROLES \\
    --slots $SLOTS \\
    --state /var/lib/fleet/agent.json \\
    --work-dir $INSTALL_DIR/work $ALLOW_SHELL $INSECURE
Restart=always
RestartSec=10
# The agent writes only to its own directories.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=$INSTALL_DIR /var/lib/fleet

[Install]
WantedBy=multi-user.target
EOF

# The token is now inside a unit file; keep it off world-readable paths.
chmod 600 /etc/systemd/system/fleet-agent.service

systemctl daemon-reload
systemctl enable --now fleet-agent.service
sleep 2

echo
if systemctl is-active --quiet fleet-agent.service; then
    echo "==> fleet-agent is running."
else
    echo "==> fleet-agent did NOT start. Recent log:"
    journalctl -u fleet-agent.service -n 25 --no-pager || true
    exit 1
fi
echo "    logs:    journalctl -u fleet-agent -f"
echo "    restart: systemctl restart fleet-agent"
