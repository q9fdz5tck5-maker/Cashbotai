#!/usr/bin/env bash
# Package the fleet into a single archive someone else can deploy.
#
#   bash fleet/pack/make_bundle.sh --out dist/
#
# The bundle is self-contained: no pip install, no internet needed to unpack,
# nothing tied to your hub or your tokens. Whoever receives it runs one script
# and has their own private fleet on their own machines.
set -euo pipefail

OUT_DIR="dist" NAME="cashbot-fleet" VERSION="" INCLUDE_INVENTORY=""

usage() {
    cat <<'EOF'
Usage: bash make_bundle.sh [options]

  --out DIR             where to write the archive (default: dist)
  --name NAME           archive base name (default: cashbot-fleet)
  --version V           version string (default: date stamp)
  --include-inventory   bundle fleet.servers.json too

By default your server inventory is EXCLUDED, because it names your machines.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --out) OUT_DIR="$2"; shift 2 ;;
        --name) NAME="$2"; shift 2 ;;
        --version) VERSION="$2"; shift 2 ;;
        --include-inventory) INCLUDE_INVENTORY=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage; exit 2 ;;
    esac
done

VERSION="${VERSION:-$(date +%Y%m%d)}"
FLEET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

BUNDLE="$NAME-$VERSION"
mkdir -p "$STAGE/$BUNDLE"

echo "==> Staging fleet source"
for item in fleet_hub.py fleet_agent.py fleet.py fleetlib handlers drivers \
            deploy pack tests __init__.py README.md fleet.servers.example.json; do
    [[ -e "$FLEET_DIR/$item" ]] && cp -r "$FLEET_DIR/$item" "$STAGE/$BUNDLE/"
done

# Never ship caches, state, or someone's live credentials.
find "$STAGE/$BUNDLE" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/$BUNDLE" -name '*.pyc' -delete 2>/dev/null || true
rm -f "$STAGE/$BUNDLE/fleet-agent.json" "$STAGE/$BUNDLE/fleet.db"

if [[ -n "$INCLUDE_INVENTORY" && -f "$FLEET_DIR/../fleet.servers.json" ]]; then
    echo "==> WARNING: including your server inventory in the bundle"
    cp "$FLEET_DIR/../fleet.servers.json" "$STAGE/$BUNDLE/"
fi

cat > "$STAGE/$BUNDLE/INSTALL.md" <<'EOF'
# Install your own fleet

You need one machine that other machines can reach (the **hub**), and any
number of worker machines. Workers can be VPS boxes, spare desktops, or
anything on your home network -- they only make outbound connections, so they
need no port forwarding and no public IP.

## 1. The hub

On a server with a public DNS name:

    sudo bash deploy/bootstrap_hub.sh --domain hub.yourdomain.com

It prints three values. Save them; they are shown once.

Port 443 is not a stylistic choice. If you intend to drive this from the
Claude app, the hub must answer on 443 -- it is the only outbound port that
environment permits.

No public server? Run the hub on your LAN and use `--no-tls`, then drive it
from a machine on the same network.

## 2. Each worker

    sudo bash deploy/bootstrap_agent.sh \
        --hub https://hub.yourdomain.com \
        --enroll-token <the enroll token> \
        --name video-01 --roles video --slots 2

Give each box the role matching its job: `audio`, `video`, `webinar`, or your
own names. A box only ever receives work for roles it declares.

## 3. Drive it

    export FLEET_HUB=https://hub.yourdomain.com
    export FLEET_TOKEN=<the admin token>

    python3 fleet.py preflight     # confirms reachability, names the problem
    python3 fleet.py status
    python3 fleet.py webinar my-script.json

## Adding your own work types

`handlers/` holds one module per job kind. Write a function
`run(payload, ctx) -> dict`, register it in `handlers/__init__.py`, and every
worker that picks up the bundle can run it.
EOF

echo "==> Building archives"
mkdir -p "$OUT_DIR"
OUT_ABS="$(cd "$OUT_DIR" && pwd)"

tar -czf "$OUT_ABS/$BUNDLE.tar.gz" -C "$STAGE" "$BUNDLE"
if command -v zip >/dev/null 2>&1; then
    (cd "$STAGE" && zip -qr "$OUT_ABS/$BUNDLE.zip" "$BUNDLE")
fi

echo
echo "Wrote:"
for f in "$OUT_ABS/$BUNDLE.tar.gz" "$OUT_ABS/$BUNDLE.zip"; do
    [[ -f "$f" ]] && printf '  %s  (%s)\n' "$f" "$(du -h "$f" | cut -f1)"
done
if command -v sha256sum >/dev/null 2>&1; then
    (cd "$OUT_ABS" && sha256sum "$BUNDLE".* > "$BUNDLE.sha256")
    echo "  $OUT_ABS/$BUNDLE.sha256"
fi
