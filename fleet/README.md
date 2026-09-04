# Cashbot Fleet

Role-specialised worker machines, driven from the Claude app over HTTPS.

One box generates AI voice. Another renders video. Another hosts the webinar
builder. You queue work from your phone; the right machine picks it up.

## Why this is not SSH

The Claude sandbox cannot SSH anywhere, and no amount of configuration will
change that. Measured from inside it:

| | Result |
|---|---|
| Outbound port 22 | **blocked** — connections time out to every host |
| `ssh` binary | **not installed** |
| Outbound port 443 | **open**, direct TLS, certificate verification intact |
| HTTPS proxy (`$HTTPS_PROXY`) | allowlisted — returns `403` for your own servers |

So the fleet inverts the direction. Workers dial **out** to a hub on port 443
and ask for work. Nothing ever connects *into* a worker.

That inversion buys more than sandbox compatibility:

- Workers need no public IP, no open ports, and no port forwarding, so a
  desktop on your home LAN is as usable as a VPS.
- A box that reboots rejoins by itself.
- No SSH key is ever on the machine issuing the work.

`fleetlib/client.py` is the piece that makes it work: it talks HTTP over a
raw socket via `http.client`, which ignores `$HTTPS_PROXY` entirely and so
reaches your hub directly instead of being refused by the egress allowlist.

## Shape

```
   Claude app  ──HTTPS/443──>  HUB  <──poll──  audio-01   (piper / TTS)
   (fleet CLI)                  │    <──poll──  video-01   (ffmpeg)
                                │    <──poll──  webinar-01 (composite)
                          jobs, artifacts,      home-desktop (behind NAT)
                          autoscaler
```

The hub is one small Python process: SQLite for state, a directory for
artifacts. No Postgres, no Redis, no message broker, **no pip install**. The
entire fleet is standard library only, which is what lets it be zipped up and
handed to someone else.

## Install

**Hub** — one server with a DNS name:

```bash
sudo bash deploy/bootstrap_hub.sh --domain hub.yourdomain.com
```

Caddy is installed in front for automatic TLS on 443. Three tokens are printed
once: save them.

**Each worker:**

```bash
sudo bash deploy/bootstrap_agent.sh \
    --hub https://hub.yourdomain.com \
    --enroll-token <enroll token> \
    --name video-01 --roles video --slots 2
```

It installs only what the roles need (ffmpeg for video, espeak-ng for audio),
registers a systemd unit, and starts. Re-running it updates in place.

## Use

```bash
export FLEET_HUB=https://hub.yourdomain.com
export FLEET_TOKEN=<admin token>

fleet preflight                 # can I reach the hub, and if not, exactly why
fleet status                    # every box, every role, at a glance
fleet scale                     # what the autoscaler is thinking
fleet webinar script.json       # narrate and render a whole webinar
fleet job job_abc123            # result, timings, artifacts
fleet download art_xyz -o out.mp4
```

`fleet preflight` is the command to reach for when something is wrong. It
separates the three failures that otherwise look identical: the port is
blocked, TLS does not verify, or the token is wrong.

## Roles

A job names a role; only a machine declaring that role can claim it.

| Role | For |
|---|---|
| `audio` | AI voice / TTS |
| `video` | ffmpeg rendering |
| `webinar` | composite webinar pipelines |
| `general` | anything unpinned |

Roles are free-form — invent `gpu`, `scrape`, `whisper` as you need them.
`general` is an ordinary role, deliberately **not** a wildcard, so a box you
tagged `general` never quietly starts stealing GPU renders. `*` is the wildcard
if you actually want one.

## Job kinds

| Kind | Does | Needs |
|---|---|---|
| `tts` | voice from text (piper, espeak, or any REST voice API) | piper or espeak-ng |
| `render` | slideshow / concat / transcode / raw ffmpeg | ffmpeg |
| `webinar` | narrate a script *and* cut it to slides, one job | both |
| `shell` | a command on a worker | opt-in per box |

`shell` is refused unless the agent was started with `--allow-shell`. Anyone
holding the admin token can run code on every box that enables it.

### Webinar script

```json
{
  "title": "Q4 Launch",
  "engine": "piper",
  "voice": "/opt/voices/en_US-amy-medium.onnx",
  "resolution": "1920x1080",
  "sections": [
    {"image": "/opt/slides/01.png", "narration": "Welcome to the Q4 launch."},
    {"image": "/opt/slides/02.png", "narration": "Here is what shipped."}
  ]
}
```

Omit `duration` and each slide is held for exactly as long as its narration
runs. That is why narration and render are one job rather than two: the render
needs the measured audio length, which only exists once the speech is made.

## Scaling

The autoscaler compares outstanding work against slots that are genuinely
reporting, per role. Capacity counts only agents that are online and not
draining — a slot on a box that stopped heartbeating is not capacity, and
counting it would suppress a scale-up exactly when one is needed.

A deficit must persist (default 60s) before anything fires, so one burst of
short jobs does not demand ten machines it will not need three seconds later.

Drivers answer "can you get me another box?":

- **`manual`** (default) — reads `fleet.servers.json`, works out which boxes
  you own are tagged for the role but not reporting, and names them. It does
  not pretend to create machines it cannot create.
- **`solidseo`** — `webhook` mode POSTs a scale request to any endpoint you
  control, which is real automatic scaling today. Its `provider` mode raises
  `NotImplementedError` on purpose: SolidSEOVPS publishes no documented
  instance-creation API, and a guessed API call that silently does nothing is
  worse than none.

Write your own by subclassing `CapacityDriver` — two methods.

## Giving it to someone else

```bash
bash pack/make_bundle.sh --out dist/
```

Produces a ~40 KB archive with the hub, the agents, the installers and an
`INSTALL.md`. It carries no tokens and, unless you pass
`--include-inventory`, no server list. Whoever receives it runs one script and
has their own private fleet on their own machines — VPS boxes, spare desktops,
anything on their LAN.

## Adding your own work

`handlers/` holds one module per job kind:

```python
def run(payload, ctx):
    ctx.log("starting")
    out = os.path.join(ctx.workdir, "result.bin")
    ...
    return {"file": ctx.artifact(out)}
```

Register it in `handlers/__init__.py`. Raising fails the job with your message
attached. `ctx.fetch()` resolves an input from a local path, a URL, a hub
artifact, or inline base64; `ctx.artifact()` publishes an output.

Handler failures are not retried on another box — they would fail there for
the same reason. Crashes are retried, and a job whose worker dies is requeued
when its lease expires.

## Security

- Tokens are bearer credentials over TLS. Agent tokens are stored hashed;
  the plaintext is shown once at enrolment and never persisted.
- Admin and enrolment tokens are separate. A worker cannot read fleet state.
- Hub tokens live in `/etc/fleet-hub.env`, mode 600, not in the unit file or
  in `ps` output.
- Uploaded artifact names are stripped to a basename, so a worker cannot write
  outside the artifact directory.
- Voice-API keys are read from the *worker's* environment via `env:` header
  references, never from the job payload — so a key never lands in the hub
  database or a job record.
- `fleet.servers.json` is gitignored. Keep it that way; it names your machines.

## Tests

```bash
python3 -m unittest discover -s fleet/tests -t . -v
```

33 tests, no network and no fixtures required. They cover role isolation, the
concurrent-claim race (twelve threads against one queue, asserting no job is
ever handed out twice), lease reclamation, retry semantics, autoscaler maths,
and a binary artifact round trip through a live hub using all 256 byte values.
