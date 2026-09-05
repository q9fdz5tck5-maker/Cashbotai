"""Model Context Protocol server for the fleet.

This is the piece that lets somebody drive their machines by *talking to
Claude* instead of by typing commands. Claude speaks MCP; this module answers
in it, and every tool underneath is a call to the fleet hub.

Two transports carry the same tools, because the two ways people actually use
Claude need different ones:

``fleet_mcp.py``            stdio, for Claude Code on the main computer. Claude
                            launches this file as a subprocess and talks to it
                            over the pipe.
``POST /mcp`` on the hub    plain HTTP JSON-RPC, for adding the fleet to the
                            Claude app as a custom connector, so the phone can
                            drive it with nothing installed.

Both call :func:`dispatch`, so a tool cannot exist in one and be missing from
the other.

Tool names are written for the person watching Claude use them -- ``speak_text``
and ``list_computers`` rather than ``tts_submit`` and ``get_agents``. Somebody
who has never opened a terminal reads "Claude used list_computers" and knows
what happened.
"""

import json
import os
import time

from .client import FleetClient, FleetError, Unauthorized

# The versions of the protocol this server knows how to speak. A client asks
# for one in `initialize`; we echo it back when we know it, and otherwise fall
# back to the newest we support -- which the spec requires, and which is what
# keeps this working when the Claude app moves to a newer revision.
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = SUPPORTED_PROTOCOLS[0]

SERVER_NAME = "cashbot-fleet"
SERVER_VERSION = "1.0.0"

# JSON-RPC 2.0 error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

TERMINAL = {"done", "failed", "cancelled"}

# How long a tool call may block before it hands back a job id instead. The
# Claude app gives a tool call a limited window; a render that takes four
# minutes has to be polled rather than waited on, or the call dies holding the
# only reference to the job.
QUICK_WAIT = 120
POLL_INTERVAL = 2.0


class ToolError(Exception):
    """A tool failed in a way the user should read, not a crash."""


# ---------------------------------------------------------------- tools ----

def _client(ctx):
    """The hub client for this session, built once and reused."""
    client = ctx.get("client")
    if client is None:
        raise ToolError(
            "This server has no hub to talk to. Set FLEET_HUB and FLEET_TOKEN "
            "before starting it."
        )
    return client


def _ago(seconds):
    if seconds is None:
        return "-"
    seconds = float(seconds)
    for limit, unit, size in ((60, "s", 1), (3600, "m", 60),
                              (86400, "h", 3600)):
        if seconds < limit:
            return "%d%s" % (int(seconds / size), unit)
    return "%dd" % int(seconds / 86400)


def tool_list_computers(args, ctx):
    """Every machine in the fleet and what it is doing."""
    status = _client(ctx).get("/v1/status")
    agents = status.get("agents") or []
    if not agents:
        return (
            "No computers have joined yet.\n\n"
            "Add one by running this on it:\n"
            "    sudo bash setup.sh --helper --hub %s --code <helper code>\n"
            "The helper code is in MY-FLEET-DETAILS.txt on the main computer."
            % ctx.get("hub_url", "https://your-main-computer")
        )
    lines = ["%d computer%s:" % (len(agents), "" if len(agents) == 1 else "s"),
             ""]
    for agent in agents:
        state = agent.get("state", "?")
        if agent.get("draining"):
            state += " (finishing up, taking no new work)"
        lines.append(
            "  %-16s  %-28s  %s, %s slot(s), last seen %s ago"
            % (agent.get("name", "?"),
               ",".join(agent.get("roles") or []) or "-",
               state, agent.get("slots", "?"),
               _ago(agent.get("last_seen_ago"))))
    busy = [
        "  %-10s  %s waiting, %s running, %s slot(s) free"
        % (role, s.get("queued", 0), s.get("running", 0), s.get("capacity", 0))
        for role, s in sorted((status.get("roles") or {}).items())
        if s.get("queued") or s.get("running") or s.get("capacity")
    ]
    if busy:
        lines += ["", "Work:"] + busy
    return "\n".join(lines)


def tool_check_connection(args, ctx):
    """Say plainly whether the hub is reachable, and if not, which of the
    three usual problems it is."""
    client = _client(ctx)
    report = client.preflight()
    lines = ["Main computer: %s://%s:%s"
             % (report["scheme"], report["host"], report["port"]),
             "  can open a connection: %s" % report.get("tcp")]
    if "tls" in report:
        lines.append("  secure (https):        %s %s"
                     % (report.get("tls"), report.get("tls_version", "")))
    lines.append("  your code accepted:    %s" % report.get("auth", "-"))
    hub = report.get("hub")
    if isinstance(hub, dict):
        lines.append("  main computer is up:   yes, for %s"
                     % _ago(hub.get("uptime_seconds")))
    if report.get("advice"):
        lines += ["", report["advice"]]
    else:
        lines += ["", "Everything is working."]
    return "\n".join(lines)


def _submit(ctx, role, kind, payload, priority=0, timeout=3600):
    return _client(ctx).post("/v1/jobs", {
        "role": role, "kind": kind, "payload": payload,
        "priority": priority, "timeout_seconds": timeout,
    })


def _describe_job(job, ctx, note=""):
    """One block of text about a job, written to be read aloud by Claude."""
    lines = ["Job %s -- %s" % (job["id"], job["status"])]
    if note:
        lines.append(note)
    if job.get("error"):
        lines.append("It failed: %s" % job["error"])
    artifacts = job.get("artifacts") or []
    if artifacts:
        lines.append("")
        lines.append("Finished file%s:" % ("" if len(artifacts) == 1 else "s"))
        for art in artifacts:
            lines.append("  %s   %s   %.2f MB"
                         % (art["id"], art["name"], art["size"] / 1048576.0))
        lines.append("")
        lines.append("Use save_result with id %s to write it to a file."
                     % artifacts[0]["id"])
    elif job["status"] not in TERMINAL:
        lines.append("Still going. Use check_job with id %s to look again."
                     % job["id"])
    return "\n".join(lines)


def _wait_for(ctx, job_id, seconds):
    """Poll a job until it finishes or the budget runs out."""
    client = _client(ctx)
    deadline = time.time() + max(0, seconds)
    job = client.get("/v1/jobs/%s" % job_id)
    while job["status"] not in TERMINAL and time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        job = client.get("/v1/jobs/%s" % job_id)
    return job


def tool_speak_text(args, ctx):
    """Read words out loud in an AI voice."""
    text = (args.get("text") or "").strip()
    if not text:
        raise ToolError("speak_text needs some 'text' to say.")
    payload = {"text": text, "engine": args.get("engine") or "piper"}
    if args.get("voice"):
        payload["voice"] = args["voice"]
    job = _submit(ctx, args.get("role") or "audio", "tts", payload, timeout=1800)
    job = _wait_for(ctx, job["id"], args.get("wait_seconds", QUICK_WAIT))
    job = _client(ctx).get("/v1/jobs/%s" % job["id"])
    return _describe_job(job, ctx,
                         note="Speaking %d characters." % len(text))


def tool_make_video(args, ctx):
    """Build a narrated video out of written sections."""
    sections = args.get("sections")
    if not sections:
        raise ToolError(
            "make_video needs a 'sections' list. Each section is one slide: "
            "give it a 'narration' (the words spoken over it) plus either a "
            "'title' with 'bullets', or kind='diagram' with 'boxes'."
        )
    payload = {
        "title": args.get("title") or "video",
        "engine": args.get("engine") or "piper",
        "resolution": args.get("resolution") or "1920x1080",
        "theme": args.get("theme") or "dark",
        "sections": sections,
    }
    if args.get("voice"):
        payload["voice"] = args["voice"]
    job = _submit(ctx, args.get("role") or "webinar", "webinar", payload,
                  timeout=7200)
    job = _wait_for(ctx, job["id"], args.get("wait_seconds", QUICK_WAIT))
    job = _client(ctx).get("/v1/jobs/%s" % job["id"])
    return _describe_job(
        job, ctx,
        note="Making a video from %d section(s). A long one takes a few "
             "minutes -- check back with check_job." % len(sections))


def tool_make_slide(args, ctx):
    """Draw one slide image from words."""
    spec = dict(args.get("slide") or {})
    if not spec:
        raise ToolError(
            "make_slide needs a 'slide' object: {title, subtitle, bullets} or "
            "{kind:'diagram', title, boxes:[{label,note}], arrows:'loop'}."
        )
    payload = {"slides": [spec],
               "resolution": args.get("resolution") or "1920x1080",
               "theme": args.get("theme") or "dark"}
    job = _submit(ctx, args.get("role") or "video", "deck", payload, timeout=900)
    job = _wait_for(ctx, job["id"], args.get("wait_seconds", QUICK_WAIT))
    job = _client(ctx).get("/v1/jobs/%s" % job["id"])
    return _describe_job(job, ctx)


def tool_run_job(args, ctx):
    """The escape hatch: queue any job kind with any payload."""
    kind = (args.get("kind") or "").strip()
    role = (args.get("role") or "").strip()
    if not kind or not role:
        raise ToolError("run_job needs both a 'role' and a 'kind'.")
    payload = args.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError as exc:
            raise ToolError("'payload' was a string but not valid JSON: %s" % exc)
    job = _submit(ctx, role, kind, payload or {},
                  priority=int(args.get("priority") or 0),
                  timeout=int(args.get("timeout_seconds") or 3600))
    if args.get("wait_seconds"):
        job = _wait_for(ctx, job["id"], int(args["wait_seconds"]))
        job = _client(ctx).get("/v1/jobs/%s" % job["id"])
    return _describe_job(job, ctx)


def tool_check_job(args, ctx):
    """How is one job doing."""
    job_id = (args.get("job_id") or "").strip()
    if not job_id:
        raise ToolError("check_job needs a 'job_id'.")
    if args.get("wait_seconds"):
        _wait_for(ctx, job_id, int(args["wait_seconds"]))
    job = _client(ctx).get("/v1/jobs/%s" % job_id)
    extra = []
    if job.get("started_at"):
        end = job.get("finished_at") or time.time()
        extra.append("Ran for %s." % _ago(end - job["started_at"]))
    if job.get("result"):
        extra.append("Result: %s" % json.dumps(job["result"])[:600])
    return _describe_job(job, ctx, note=" ".join(extra))


def tool_list_jobs(args, ctx):
    """Recent work, newest first."""
    jobs = _client(ctx).get("/v1/jobs", params={
        "status": args.get("status"),
        "role": args.get("role"),
        "limit": min(int(args.get("limit") or 20), 100),
    })["jobs"]
    if not jobs:
        return "Nothing has been queued yet."
    lines = []
    for job in jobs:
        lines.append("  %-22s %-9s %-9s %-10s %s ago"
                     % (job["id"], job["role"], job["kind"], job["status"],
                        _ago(time.time() - job["created_at"])))
    return "%d job(s):\n\n%s" % (len(jobs), "\n".join(lines))


def tool_save_result(args, ctx):
    """Write a finished file to disk on this machine."""
    artifact_id = (args.get("artifact_id") or "").strip()
    if not artifact_id:
        raise ToolError("save_result needs an 'artifact_id' (check_job shows them).")
    path = args.get("save_as") or artifact_id
    path = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(path) or "."
    if not os.path.isdir(parent):
        raise ToolError("There is no folder at %s to save into." % parent)
    data = _client(ctx).get_bytes("/v1/artifacts/%s" % artifact_id, timeout=600)
    with open(path, "wb") as handle:
        handle.write(data)
    return "Saved %s (%.2f MB) to %s" % (artifact_id, len(data) / 1048576.0, path)


def tool_cancel_job(args, ctx):
    """Stop a job that is queued or running."""
    job_id = (args.get("job_id") or "").strip()
    if not job_id:
        raise ToolError("cancel_job needs a 'job_id'.")
    result = _client(ctx).post("/v1/jobs/%s/cancel" % job_id)
    if result.get("cancelled"):
        return "Cancelled %s." % job_id
    return "Could not cancel %s: %s" % (job_id, result.get("detail"))


def tool_add_computer(args, ctx):
    """The exact line to paste on a new machine to make it join."""
    hub = ctx.get("hub_url") or "https://your-main-computer"
    code = ctx.get("enroll_token")
    job = (args.get("good_at") or "everything").lower()
    if job not in ("voice", "video", "everything"):
        raise ToolError("'good_at' must be voice, video, or everything.")
    lines = ["On the new computer, unpack the zip, then paste this line:", ""]
    if code:
        lines.append("    sudo bash setup.sh --helper --hub %s --code %s --job %s"
                     % (hub, code, job))
    else:
        lines += [
            "    sudo bash setup.sh --helper --hub %s --code YOUR-HELPER-CODE "
            "--job %s" % (hub, job),
            "",
            "Replace YOUR-HELPER-CODE with the helper code from "
            "MY-FLEET-DETAILS.txt on the main computer. (This server was not "
            "given the helper code, so it cannot fill it in for you.)",
        ]
    lines += ["",
              "It takes a couple of minutes. Then ask me to list the computers "
              "and the new one will be there."]
    return "\n".join(lines)


# name -> (function, description, input schema)
TOOLS = {
    "list_computers": (
        tool_list_computers,
        "List every computer in the fleet, what each one is set up to do, and "
        "whether it is online right now. Use this first when someone asks "
        "what machines they have, whether something is connected, or why work "
        "is not being picked up.",
        {"type": "object", "properties": {}},
    ),
    "check_connection": (
        tool_check_connection,
        "Diagnose whether this machine can reach the main computer, and if it "
        "cannot, say which of the three usual problems it is: the port is "
        "blocked, the secure connection does not verify, or the access code "
        "is wrong. Use this whenever anything is failing.",
        {"type": "object", "properties": {}},
    ),
    "speak_text": (
        tool_speak_text,
        "Turn written words into spoken audio using an AI voice, on whichever "
        "computer is set up for voice. Returns a WAV file you can then save "
        "with save_result.",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "The words to say out loud."},
                "voice": {"type": "string",
                          "description": "Which voice to use. Leave this out "
                          "to use whatever the machine already has."},
                "engine": {"type": "string",
                           "enum": ["piper", "espeak", "clone", "http"],
                           "description": "piper is the normal free local "
                           "voice. clone is the user's own cloned voice, which "
                           "needs a voice-engine machine."},
                "role": {"type": "string",
                         "description": "Which kind of computer should do it. "
                         "Default 'audio'."},
                "wait_seconds": {"type": "integer",
                                 "description": "How long to wait before "
                                 "handing back a job id to poll instead."},
            },
            "required": ["text"],
        },
    ),
    "make_video": (
        tool_make_video,
        "Build a complete narrated video from written sections. Each section "
        "becomes one slide, drawn from its own words, held on screen for "
        "exactly as long as its narration takes to speak. No video editor and "
        "no image files are needed.\n\n"
        "A section is either a text slide -- 'title', optional 'subtitle', "
        "optional 'bullets' -- or a diagram: set \"kind\": \"diagram\" and "
        "give 'boxes' (up to 5, each {label, note}), optional \"person\": true "
        "for a stick figure at the left, optional 'outputs' for a numbered "
        "list underneath, optional \"arrows\": \"right\" or \"loop\", and an "
        "optional 'caption'. Every section takes a 'narration' string.\n\n"
        "Videos take minutes, so this returns a job id once it has been "
        "queued; follow it with check_job.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string",
                          "description": "Names the finished file."},
                "sections": {
                    "type": "array",
                    "description": "The slides, in order.",
                    "items": {"type": "object"},
                },
                "voice": {"type": "string"},
                "engine": {"type": "string",
                           "enum": ["piper", "espeak", "clone", "http"]},
                "resolution": {"type": "string",
                               "description": "Default 1920x1080."},
                "theme": {"type": "string", "enum": ["dark", "light"]},
                "role": {"type": "string",
                         "description": "Default 'webinar'."},
                "wait_seconds": {"type": "integer"},
            },
            "required": ["sections"],
        },
    ),
    "make_slide": (
        tool_make_slide,
        "Draw a single slide image from words -- a title with bullet points, "
        "or a diagram of labelled boxes joined by arrows. Use this to check "
        "how a slide will look before committing it to a whole video.",
        {
            "type": "object",
            "properties": {
                "slide": {
                    "type": "object",
                    "description": "{title, subtitle, bullets} for a text "
                    "slide, or {kind:'diagram', title, boxes:[{label,note}], "
                    "person, outputs, arrows, caption} for a diagram.",
                },
                "resolution": {"type": "string"},
                "theme": {"type": "string", "enum": ["dark", "light"]},
                "role": {"type": "string"},
                "wait_seconds": {"type": "integer"},
            },
            "required": ["slide"],
        },
    ),
    "run_job": (
        tool_run_job,
        "Queue any job on any computer in the fleet. This is the general "
        "escape hatch for work the other tools do not cover -- job kinds are "
        "tts, render, deck, webinar, and shell. Prefer the specific tools "
        "when one fits.",
        {
            "type": "object",
            "properties": {
                "role": {"type": "string",
                         "description": "Which kind of computer: audio, "
                         "video, webinar, general, or one you invented."},
                "kind": {"type": "string",
                         "enum": ["tts", "render", "deck", "webinar", "shell"]},
                "payload": {"type": "object",
                            "description": "The job's own settings."},
                "priority": {"type": "integer"},
                "timeout_seconds": {"type": "integer"},
                "wait_seconds": {"type": "integer"},
            },
            "required": ["role", "kind"],
        },
    ),
    "check_job": (
        tool_check_job,
        "Look at one job: whether it finished, how long it took, what it "
        "produced, and the error if it failed. Use this after make_video or "
        "any tool that handed back a job id.",
        {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "wait_seconds": {"type": "integer",
                                 "description": "Wait up to this long for it "
                                 "to finish before answering."},
            },
            "required": ["job_id"],
        },
    ),
    "list_jobs": (
        tool_list_jobs,
        "List recent work across the whole fleet, newest first. Use this when "
        "someone asks what has been running or what went wrong lately.",
        {
            "type": "object",
            "properties": {
                "status": {"type": "string",
                           "enum": ["queued", "running", "done", "failed",
                                    "cancelled"]},
                "role": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    ),
    "save_result": (
        tool_save_result,
        "Download a finished file the fleet produced and write it to disk on "
        "this machine. Get the id from check_job.",
        {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
                "save_as": {"type": "string",
                            "description": "Where to write it. Default: the "
                            "id, in the current folder."},
            },
            "required": ["artifact_id"],
        },
    ),
    "cancel_job": (
        tool_cancel_job,
        "Stop a job that is waiting or already running, so the computer "
        "doing it is freed up. Use this when someone changes their mind about "
        "something they asked for, or when a job is stuck.",
        {"type": "object", "properties": {"job_id": {"type": "string"}},
         "required": ["job_id"]},
    ),
    "add_computer": (
        tool_add_computer,
        "Give the exact command to paste on a new machine so it joins the "
        "fleet. Use this when someone says they want to add another computer.",
        {
            "type": "object",
            "properties": {
                "good_at": {"type": "string",
                            "enum": ["voice", "video", "everything"],
                            "description": "What the new machine should "
                            "specialise in. Default everything."},
            },
        },
    ),
}


def tool_definitions():
    """The `tools/list` payload."""
    return [
        {"name": name, "description": description, "inputSchema": schema}
        for name, (_fn, description, schema) in sorted(TOOLS.items())
    ]


# ------------------------------------------------------------- dispatch ----

# Where to look for settings when the environment does not carry them.
# Claude launches this server itself, and it does not inherit a login shell --
# so anything that depended on the person having opened a fresh terminal after
# setup would work when tested by hand and fail for the recipient. Reading the
# file directly removes that whole class of "it works for me".
CONFIG_FILES = (
    "~/.fleet.env",           # written by setup.sh for the person who owns it
    "/etc/fleet.env",         # a machine-wide override
    "/etc/fleet-hub.env",     # the hub's own file, on the main computer
)

# Names as they appear in those files, mapped to what this module calls them.
# The hub writes FLEET_ADMIN_TOKEN; a client calls the same string FLEET_TOKEN.
CONFIG_ALIASES = {
    "FLEET_HUB": "hub_url",
    "FLEET_TOKEN": "token",
    "FLEET_ADMIN_TOKEN": "token",
    "FLEET_ENROLL_TOKEN": "enroll_token",
    "FLEET_INSECURE": "insecure",
}


def read_config_files(paths=CONFIG_FILES):
    """Merge `KEY=value` settings from the first readable files, in order.

    Earlier files win, so a personal ~/.fleet.env overrides the machine-wide
    one. Unreadable and missing files are skipped rather than raising: on a
    worker box /etc/fleet-hub.env does not exist, and that is normal.
    """
    found = {}
    for path in paths:
        expanded = os.path.expanduser(path)
        try:
            with open(expanded, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            target = CONFIG_ALIASES.get(key)
            if target and target not in found:
                found[target] = value.strip().strip('"').strip("'")
    return found


def build_context(hub_url=None, token=None, insecure=None, enroll_token=None,
                  client=None, config_files=CONFIG_FILES):
    """Assemble the per-session state the tools read.

    A missing hub is not fatal here on purpose: Claude should be able to start
    the server, call a tool, and be *told* what is unset, rather than watch the
    connection die at launch with nothing on screen to explain it.

    Settings are taken from arguments first, then the environment, then the
    config files -- so an explicit value always wins and nothing on disk can
    quietly redirect a session that was told where to go.
    """
    from_file = read_config_files(config_files) if config_files else {}

    hub_url = hub_url or os.environ.get("FLEET_HUB") or from_file.get("hub_url")
    token = token or os.environ.get("FLEET_TOKEN") or from_file.get("token")
    enroll_token = (enroll_token or os.environ.get("FLEET_ENROLL_TOKEN")
                    or from_file.get("enroll_token"))
    if insecure is None:
        insecure = (os.environ.get("FLEET_INSECURE")
                    or from_file.get("insecure")) == "1"
    ctx = {
        "hub_url": hub_url,
        "enroll_token": enroll_token,
        "client": client,
    }
    if client is None and hub_url:
        ctx["client"] = FleetClient(
            hub_url, token=token, insecure=bool(insecure),
            ca_file=os.environ.get("FLEET_CA_FILE") or None,
        )
    return ctx


def call_tool(name, arguments, ctx):
    """Run one tool, returning the MCP `tools/call` result.

    Failures come back as ``isError`` results rather than JSON-RPC errors: the
    spec draws that line so the model *sees* the failure text and can correct
    itself, instead of the transport swallowing it.
    """
    entry = TOOLS.get(name)
    if entry is None:
        return {
            "content": [{"type": "text",
                         "text": "There is no tool called %r. Available: %s"
                                 % (name, ", ".join(sorted(TOOLS)))}],
            "isError": True,
        }
    try:
        text = entry[0](arguments or {}, ctx)
    except ToolError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    except Unauthorized:
        return {
            "content": [{"type": "text", "text":
                         "The main computer rejected the access code. Check "
                         "FLEET_TOKEN is the private code from "
                         "MY-FLEET-DETAILS.txt."}],
            "isError": True,
        }
    except FleetError as exc:
        return {
            "content": [{"type": "text",
                         "text": "The main computer answered with an error: %s"
                                 % exc}],
            "isError": True,
        }
    except Exception as exc:                       # noqa: BLE001 - reported, not swallowed
        return {
            "content": [{"type": "text",
                         "text": "%s failed: %s: %s"
                                 % (name, type(exc).__name__, exc)}],
            "isError": True,
        }
    return {"content": [{"type": "text", "text": text}], "isError": False}


def negotiate_protocol(requested):
    return requested if requested in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL


def dispatch(message, ctx):
    """Handle one JSON-RPC message. Returns a response dict, or None.

    None means "this was a notification" -- notifications carry no id and the
    spec forbids answering them. Returning a response to one is what makes a
    client hang waiting for a reply to a message it never expected.
    """
    if not isinstance(message, dict):
        return _error(None, INVALID_REQUEST, "message must be a JSON object")

    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params") or {}

    if method is None:
        return _error(message_id, INVALID_REQUEST, "missing 'method'")

    # A notification has no id. Act on it, answer nothing.
    is_notification = "id" not in message

    if method == "initialize":
        return _ok(message_id, {
            "protocolVersion": negotiate_protocol(params.get("protocolVersion")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "This is somebody's private fleet of computers. Use "
                "list_computers to see the machines, speak_text to make audio, "
                "make_video to build a narrated video, and check_job to follow "
                "anything slow. Talk about the machines in plain words -- the "
                "person using this may never have opened a terminal."
            ),
        })

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "ping":
        return None if is_notification else _ok(message_id, {})

    if method == "tools/list":
        return _ok(message_id, {"tools": tool_definitions()})

    if method == "tools/call":
        name = params.get("name")
        if not name:
            return _error(message_id, INVALID_PARAMS, "missing tool name")
        return _ok(message_id, call_tool(name, params.get("arguments"), ctx))

    # Capabilities we do not advertise. Answering "empty list" rather than
    # "method not found" keeps clients that probe for them quiet.
    if method in ("resources/list", "prompts/list"):
        key = method.split("/")[0]
        return _ok(message_id, {key: []})

    if is_notification:
        return None
    return _error(message_id, METHOD_NOT_FOUND, "unknown method %r" % method)


def _ok(message_id, result):
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id, code, message):
    return {"jsonrpc": "2.0", "id": message_id,
            "error": {"code": code, "message": message}}
