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
            deploy pack tests webinars __init__.py fleet.servers.example.json; do
    [[ -e "$FLEET_DIR/$item" ]] && cp -r "$FLEET_DIR/$item" "$STAGE/$BUNDLE/"
done

# The two files a person actually opens go at the top level, not inside pack/.
cp "$FLEET_DIR/pack/setup.sh" "$STAGE/$BUNDLE/setup.sh"
cp "$FLEET_DIR/pack/START-HERE.txt" "$STAGE/$BUNDLE/START-HERE.txt"
chmod +x "$STAGE/$BUNDLE/setup.sh"
# README.md is written for someone who already knows the words. Keep it, but
# not as the thing a newcomer opens first.
[[ -f "$FLEET_DIR/README.md" ]] && cp "$FLEET_DIR/README.md" "$STAGE/$BUNDLE/TECHNICAL.md"
# Rendered videos are output, not source; they would dwarf the archive.
rm -rf "$STAGE/$BUNDLE/webinars/out"

# Never ship caches, state, or someone's live credentials.
find "$STAGE/$BUNDLE" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/$BUNDLE" -name '*.pyc' -delete 2>/dev/null || true
rm -f "$STAGE/$BUNDLE/fleet-agent.json" "$STAGE/$BUNDLE/fleet.db"

if [[ -n "$INCLUDE_INVENTORY" && -f "$FLEET_DIR/../fleet.servers.json" ]]; then
    echo "==> WARNING: including your server inventory in the bundle"
    cp "$FLEET_DIR/../fleet.servers.json" "$STAGE/$BUNDLE/"
fi

cat > "$STAGE/$BUNDLE/INSTALL.md" <<'EOF'
# Install

Open **START-HERE.txt** first. It is one page and it is the whole thing.

The short version:

1. On the computer that the others will reach, run `sudo bash setup.sh`
   and choose 1.
2. It prints one line. Paste that line on every other computer.

That is all of it. `TECHNICAL.md` explains how it works underneath and how to
add your own kinds of work.
EOF

# ---------------------------------------------------------------------------
# Refuse to ship secrets.
#
# The bundle is meant to be handed to other people, so "it carries no tokens"
# has to be something the build enforces rather than something we remember to
# check. A leaked admin token would let whoever received the archive queue work
# on the sender's machines.
echo "==> Checking the bundle carries no secrets"
LEAKS=""
if grep -rIlE 'FLEET_(ADMIN|ENROLL)_TOKEN=.+' "$STAGE/$BUNDLE" 2>/dev/null | grep -v '\.sh$' | grep -q .; then
    LEAKS="$LEAKS\n  - a file assigns FLEET_ADMIN_TOKEN or FLEET_ENROLL_TOKEN a value"
fi
if [[ -z "$INCLUDE_INVENTORY" ]] && [[ -e "$STAGE/$BUNDLE/fleet.servers.json" ]]; then
    LEAKS="$LEAKS\n  - fleet.servers.json (your server list) is present"
fi
for stray in fleet-agent.json fleet.db MY-FLEET-DETAILS.txt; do
    if find "$STAGE/$BUNDLE" -name "$stray" -print -quit 2>/dev/null | grep -q .; then
        LEAKS="$LEAKS\n  - $stray is present"
    fi
done
if [[ -n "$LEAKS" ]]; then
    echo "ERROR: refusing to build. This bundle would ship secrets:" >&2
    printf "$LEAKS\n" >&2
    exit 1
fi
echo "    clean"

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
