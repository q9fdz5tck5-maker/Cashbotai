#!/usr/bin/env bash
# Install the fleet hub on one public server.
#
#   sudo bash bootstrap_hub.sh --domain hub.example.com
#
# Puts Caddy in front on 443 so TLS certificates are obtained and renewed
# automatically, and runs the hub on loopback behind it. Port 443 matters: it
# is the only outbound port the Claude sandbox can reach.
set -euo pipefail

DOMAIN="" INSTALL_DIR="/opt/fleet" DATA_DIR="/var/lib/fleet-hub"
DRIVER="manual" NO_TLS=""

usage() {
    cat <<'EOF'
Usage: sudo bash bootstrap_hub.sh --domain hub.example.com [options]

Options:
  --domain NAME     public DNS name pointing at this server (required for TLS)
  --no-tls          serve plain HTTP on 8443 instead (testing only)
  --driver NAME     capacity driver: manual | solidseo
  --data DIR        database and artifacts (default /var/lib/fleet-hub)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        --no-tls) NO_TLS=1; shift ;;
        --driver) DRIVER="$2"; shift 2 ;;
        --data) DATA_DIR="$2"; shift 2 ;;
        --install-dir) INSTALL_DIR="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage; exit 2 ;;
    esac
done

[[ $EUID -eq 0 ]] || { echo "ERROR: run this with sudo" >&2; exit 2; }
if [[ -z "$NO_TLS" && -z "$DOMAIN" ]]; then
    echo "ERROR: --domain is required (or pass --no-tls for local testing)" >&2
    exit 2
fi

ADMIN_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
ENROLL_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"

echo "==> Installing dependencies"
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 ca-certificates curl >/dev/null
fi

id -u fleet >/dev/null 2>&1 || useradd --system --home-dir "$INSTALL_DIR" \
    --shell /usr/sbin/nologin fleet
mkdir -p "$INSTALL_DIR" "$DATA_DIR"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp -r "$SRC_DIR"/fleet_hub.py "$SRC_DIR"/fleet.py "$SRC_DIR"/fleetlib \
      "$SRC_DIR"/drivers "$SRC_DIR"/handlers "$SRC_DIR"/__init__.py "$INSTALL_DIR"/
mkdir -p "$INSTALL_DIR/fleet"
cp -r "$SRC_DIR"/fleetlib "$SRC_DIR"/drivers "$SRC_DIR"/handlers \
      "$SRC_DIR"/__init__.py "$INSTALL_DIR/fleet"/
chown -R fleet:fleet "$INSTALL_DIR" "$DATA_DIR"

# Tokens live in an environment file readable only by root and the service,
# so they never appear in `ps` output or a world-readable unit file.
cat > /etc/fleet-hub.env <<EOF
FLEET_ADMIN_TOKEN=$ADMIN_TOKEN
FLEET_ENROLL_TOKEN=$ENROLL_TOKEN
EOF
chmod 600 /etc/fleet-hub.env

HUB_PORT=8443
cat > /etc/systemd/system/fleet-hub.service <<EOF
[Unit]
Description=Cashbot fleet hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=fleet
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=/etc/fleet-hub.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 $INSTALL_DIR/fleet_hub.py \\
    --bind 127.0.0.1 --port $HUB_PORT --data $DATA_DIR --driver $DRIVER
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOF

if [[ -z "$NO_TLS" ]]; then
    echo "==> Installing Caddy for automatic TLS on 443"
    if ! command -v caddy >/dev/null 2>&1; then
        apt-get install -y -qq debian-keyring debian-archive-keyring \
            apt-transport-https >/dev/null
        curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
            | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
        echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" \
            > /etc/apt/sources.list.d/caddy-stable.list
        apt-get update -qq && apt-get install -y -qq caddy >/dev/null
    fi
    cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
    # Long-poll job claims hold a request open; do not cut them short.
    reverse_proxy 127.0.0.1:$HUB_PORT {
        transport http {
            read_timeout 300s
        }
    }
    request_body {
        max_size 256MB
    }
}
EOF
    systemctl enable --now caddy
    systemctl reload caddy || systemctl restart caddy
    PUBLIC_URL="https://$DOMAIN"
else
    sed -i "s/--bind 127.0.0.1/--bind 0.0.0.0/" /etc/systemd/system/fleet-hub.service
    PUBLIC_URL="http://$(hostname -I | awk '{print $1}'):$HUB_PORT"
fi

systemctl daemon-reload
systemctl enable --now fleet-hub.service
sleep 2

if ! systemctl is-active --quiet fleet-hub.service; then
    echo "==> fleet-hub did NOT start. Recent log:"
    journalctl -u fleet-hub.service -n 25 --no-pager || true
    exit 1
fi

cat <<EOF

========================================================================
  Fleet hub is running at $PUBLIC_URL

  SAVE THESE NOW. They are stored only in /etc/fleet-hub.env on this box.

    FLEET_HUB=$PUBLIC_URL
    FLEET_TOKEN=$ADMIN_TOKEN          <- admin: submit jobs, read status
    FLEET_ENROLL_TOKEN=$ENROLL_TOKEN  <- give this to each worker once

  Next: add a worker.

    sudo bash fleet/deploy/bootstrap_agent.sh \\
        --hub $PUBLIC_URL \\
        --enroll-token $ENROLL_TOKEN \\
        --name video-01 --roles video --slots 2

  Then from anywhere:  fleet status
========================================================================
EOF
