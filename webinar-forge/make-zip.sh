#!/usr/bin/env bash
# Build the distributable zip.
#
# Excludes node_modules, build output, the engine venv, .env and — deliberately —
# every voice sample. See engine/voices/README.md for why.
#
#   ./make-zip.sh                  -> webinar-forge-<version>.zip
#   ./make-zip.sh --with-voices    -> includes engine/voices/*  (read the warning)

set -euo pipefail
cd "$(dirname "$0")"

VERSION="$(cat VERSION)"
NAME="webinar-forge-${VERSION}"
OUT="${NAME}.zip"
WITH_VOICES=0
[ "${1:-}" = "--with-voices" ] && WITH_VOICES=1

command -v zip >/dev/null 2>&1 || { echo "zip is not installed (apt-get install zip)"; exit 1; }

rm -f "$OUT"

EXCLUDES=(
  "*/node_modules/*" "node_modules/*"
  "*/output/*"       "output/*"
  "*/engine/.venv/*" "engine/.venv/*"
  "*/engine/data/*"  "engine/data/*"
  "*.zip" ".env" "*/.git/*" ".git/*" "*.DS_Store"
)
if [ "$WITH_VOICES" -eq 0 ]; then
  EXCLUDES+=("engine/voices/*.wav" "engine/voices/*.mp3" "engine/voices/*.m4a" "engine/voices/*.ogg")
else
  echo "WARNING: bundling voice samples. Anyone with this zip can synthesize those voices."
fi

ARGS=()
for e in "${EXCLUDES[@]}"; do ARGS+=("-x" "$e"); done

# Zip from the parent so the archive expands into a single named directory.
HERE="$(basename "$PWD")"
( cd .. && zip -r -q "${HERE}/${OUT}" "$HERE" "${ARGS[@]}" )

echo "Built ${OUT}  ($(du -h "$OUT" | cut -f1))"
echo
echo "On the target server:"
echo "  unzip ${OUT} && cd ${HERE} && ./install.sh"
