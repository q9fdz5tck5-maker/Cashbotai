#!/bin/sh
# Renders the CASH.BOT media kit to PDF (requires Chromium)
CHROME="${CHROME:-/opt/pw-browsers/chromium}"
"$CHROME" --headless=new --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf="CASH.BOT-MEDIA-KIT-2026.pdf" "file://$(pwd)/mediakit.html"
