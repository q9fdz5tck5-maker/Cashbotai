#!/usr/bin/env bash
# The only command anybody needs to run.
#
#   sudo bash setup.sh
#
# Asks a couple of plain questions and sets the machine up. Everything it does
# is also available as flags for people who prefer them -- see --help -- but
# the point of this file is that nobody has to know they exist.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# In the bundle this file sits beside deploy/. In the source tree it sits one
# level down in pack/, so look there too rather than only working when packed.
if [[ -d "$HERE/deploy" ]]; then
    DEPLOY="$HERE/deploy"
elif [[ -d "$HERE/../deploy" ]]; then
    DEPLOY="$(cd "$HERE/../deploy" && pwd)"
else
    echo "ERROR: cannot find the deploy/ directory next to setup.sh." >&2
    echo "       Unpack the whole archive and run setup.sh from inside it." >&2
    exit 1
fi
DRY_RUN="" MODE="" DOMAIN="" HUB="" CODE="" NAME="" JOB=""

usage() {
    cat <<'EOF'
Usage: sudo bash setup.sh [options]

With no options it asks you what you want, which is the intended way to use it.

  --main --domain NAME        set this machine up as the main computer
  --helper --hub URL --code T set this machine up as a helper
  --name NAME                 what to call this helper (default: its hostname)
  --job voice|video|everything what this helper should be good at
  --dry-run                   show what would happen, change nothing
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --main) MODE="main"; shift ;;
        --helper) MODE="helper"; shift ;;
        --domain) DOMAIN="$2"; shift 2 ;;
        --hub) HUB="$2"; shift 2 ;;
        --code) CODE="$2"; shift 2 ;;
        --name) NAME="$2"; shift 2 ;;
        --job) JOB="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "I do not know the option $1" >&2; usage; exit 2 ;;
    esac
done

say()  { printf '%s\n' "$*"; }
rule() { printf '%s\n' "------------------------------------------------------------"; }

# Everything this script does installs software and creates a background
# service, which on Linux requires administrator rights.
if [[ -z "$DRY_RUN" && $EUID -ne 0 ]]; then
    rule
    say "This needs administrator rights to install things."
    say
    say "Run this instead -- it is the same line with 'sudo' in front:"
    say
    say "    sudo bash $0"
    say
    say "It will ask for your password. That is normal."
    rule
    exit 2
fi

ask() {
    # ask <variable> <question> [default]
    local __var="$1" __question="$2" __default="${3:-}" __reply=""
    while true; do
        if [[ -n "$__default" ]]; then
            read -r -p "$__question [$__default]: " __reply || true
            __reply="${__reply:-$__default}"
        else
            read -r -p "$__question: " __reply || true
        fi
        __reply="${__reply#"${__reply%%[![:space:]]*}"}"
        __reply="${__reply%"${__reply##*[![:space:]]}"}"
        [[ -n "$__reply" ]] && break
        say "  (that one cannot be left blank)"
    done
    printf -v "$__var" '%s' "$__reply"
}

run() {
    if [[ -n "$DRY_RUN" ]]; then
        say "[dry run] would run: $*"
        return 0
    fi
    "$@"
}

if [[ -z "$MODE" ]]; then
    rule
    say "  Setting up your computers"
    rule
    say
    say "You are going to end up with one MAIN computer and any number of"
    say "HELPER computers. The main one keeps the list of work. The helpers"
    say "do the work. You only ever talk to the main one."
    say
    say "  1) This is my MAIN computer   (pick this first, and only once)"
    say "  2) This is a HELPER computer  (pick this on every other machine)"
    say
    ask REPLY "Type 1 or 2"
    case "$REPLY" in
        1) MODE="main" ;;
        2) MODE="helper" ;;
        *) say "That was not 1 or 2. Start again."; exit 2 ;;
    esac
    say
fi

# ---------------------------------------------------------------- main -----
if [[ "$MODE" == "main" ]]; then
    if [[ -z "$DOMAIN" ]]; then
        say "Your main computer needs a web address so the helpers can find it."
        say "Something like: fleet.yourdomain.com"
        say
        say "It has to already point at this computer. If you have not done"
        say "that yet, stop here, set it up with whoever sells you your domain,"
        say "and come back. This takes a few minutes to start working."
        say
        ask DOMAIN "Web address for this computer"
    fi
    if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$ ]]; then
        say
        say "'$DOMAIN' does not look like a web address."
        say "It should look like fleet.yourdomain.com -- no https://, no slash."
        exit 2
    fi

    say
    say "Setting up the main computer at $DOMAIN. This takes a few minutes."
    say
    run bash "$DEPLOY/bootstrap_hub.sh" --domain "$DOMAIN"

    if [[ -n "$DRY_RUN" ]]; then
        say "[dry run] would save your details and print the helper command"
        exit 0
    fi

    # bootstrap_hub.sh writes the two secrets here; read them back so the
    # helper command below can be printed ready to paste, rather than asking
    # someone to copy a long random string out of the scrollback by eye.
    ADMIN="" ENROLL=""
    if [[ -r /etc/fleet-hub.env ]]; then
        ADMIN="$(sed -n 's/^FLEET_ADMIN_TOKEN=//p' /etc/fleet-hub.env)"
        ENROLL="$(sed -n 's/^FLEET_ENROLL_TOKEN=//p' /etc/fleet-hub.env)"
    fi

    # Keep a copy somewhere the person can actually find it again.
    TARGET_HOME="$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)"
    TARGET_HOME="${TARGET_HOME:-/root}"
    DETAILS="$TARGET_HOME/MY-FLEET-DETAILS.txt"
    cat > "$DETAILS" <<EOF
Your fleet details. Keep this file. Do not post it anywhere.

Your main computer:   https://$DOMAIN

Your private code (this is like a password -- keep it secret):
    $ADMIN

The code you give each helper computer:
    $ENROLL

To add a helper computer, run this on that computer:

    sudo bash setup.sh --helper --hub https://$DOMAIN --code $ENROLL

EOF
    chmod 600 "$DETAILS"
    chown "${SUDO_USER:-root}" "$DETAILS" 2>/dev/null || true

    rule
    say "  Your main computer is ready."
    rule
    say
    say "Everything you need is saved here, so you do not have to write it down:"
    say
    say "    $DETAILS"
    say
    say "Now add a helper. Copy this whole line, go to another computer,"
    say "and paste it there:"
    say
    say "    sudo bash setup.sh --helper --hub https://$DOMAIN --code $ENROLL"
    say
    say "You can add as many helpers as you like. Same line every time."
    rule
    exit 0
fi

# -------------------------------------------------------------- helper -----
if [[ -z "$HUB" ]]; then
    say "What is the web address of your main computer?"
    say "It is in the MY-FLEET-DETAILS.txt file on that machine."
    say
    ask HUB "Web address"
fi
[[ "$HUB" =~ ^https?:// ]] || HUB="https://$HUB"
HUB="${HUB%/}"

if [[ -z "$CODE" ]]; then
    say
    say "And the code for helpers -- it is in that same file."
    say
    ask CODE "Helper code"
fi

if [[ -z "$JOB" ]]; then
    say
    say "What should this computer be good at?"
    say
    say "  1) Speaking out loud   (needs very little power)"
    say "  2) Making videos       (the more power the better)"
    say "  3) Everything          (pick this if you are not sure)"
    say
    ask REPLY "Type 1, 2 or 3" "3"
    case "$REPLY" in
        1) JOB="voice" ;;
        2) JOB="video" ;;
        3) JOB="everything" ;;
        *) say "That was not 1, 2 or 3. Start again."; exit 2 ;;
    esac
fi

case "$JOB" in
    voice)      ROLES="audio" ;;
    video)      ROLES="video" ;;
    everything) ROLES="audio,video,webinar,general" ;;
    *) say "I do not know the job '$JOB'. Use voice, video or everything."; exit 2 ;;
esac

NAME="${NAME:-$(hostname)}"

say
say "Setting this computer up as a helper called '$NAME'."
say "It will connect to $HUB and wait for work."
say
run bash "$DEPLOY/bootstrap_agent.sh" \
    --hub "$HUB" --enroll-token "$CODE" \
    --name "$NAME" --roles "$ROLES" --slots 2

if [[ -n "$DRY_RUN" ]]; then
    say "[dry run] would finish here"
    exit 0
fi

rule
say "  This computer is now a helper."
rule
say
say "It runs quietly in the background from now on, including after you"
say "restart the computer. There is nothing to leave open and nothing to"
say "click. You can close this window."
say
say "To check on it later:      systemctl status fleet-agent"
say "To see what it is doing:   journalctl -u fleet-agent -f"
say
say "Go back to your main computer and run 'fleet status'. This machine"
say "should be in the list within about half a minute."
rule
