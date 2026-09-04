#!/usr/bin/env python3
"""fleet -- command line for the whole fleet.

This is the surface you drive from the Claude app. Output is deliberately
narrow and table-shaped so it stays readable on a phone screen.

    export FLEET_HUB=https://hub.example.com
    export FLEET_TOKEN=<admin token>

    fleet preflight                 can I reach the hub, and if not, why
    fleet status                    every box and every role at a glance
    fleet submit --role audio --kind tts --payload '{"text":"hi"}'
    fleet watch job_abc123          follow a job to completion
    fleet webinar script.json       narrate and render a whole webinar
    fleet scale                     what the autoscaler is thinking
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fleetlib.client import FleetClient, FleetError, Unauthorized   # noqa: E402
from fleetlib.roles import KNOWN_ROLES                              # noqa: E402

TERMINAL = {"done", "failed", "cancelled"}


# -- presentation --------------------------------------------------------

def table(rows, headers):
    """Render a compact fixed-width table."""
    if not rows:
        return "(none)"
    widths = [len(h) for h in headers]
    cells = []
    for row in rows:
        rendered = [("" if c is None else str(c)) for c in row]
        cells.append(rendered)
        for i, cell in enumerate(rendered):
            widths[i] = max(widths[i], len(cell))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    out = [line, "  ".join("-" * w for w in widths)]
    for rendered in cells:
        out.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(rendered)))
    return "\n".join(out)


def ago(seconds):
    if seconds is None:
        return "-"
    seconds = float(seconds)
    if seconds < 60:
        return "%ds" % int(seconds)
    if seconds < 3600:
        return "%dm" % int(seconds / 60)
    if seconds < 86400:
        return "%dh" % int(seconds / 3600)
    return "%dd" % int(seconds / 86400)


def client_from(args):
    return FleetClient.from_env(
        base_url=args.hub or os.environ.get("FLEET_HUB"),
        token=args.token or os.environ.get("FLEET_TOKEN"),
        insecure=args.insecure or os.environ.get("FLEET_INSECURE") == "1",
    )


# -- commands ------------------------------------------------------------

def cmd_preflight(args):
    """Say plainly whether this machine can drive the fleet, and why not."""
    client = client_from(args)
    report = client.preflight()
    print("hub:  %s://%s:%s" % (report["scheme"], report["host"], report["port"]))
    print("tcp:  %s" % report.get("tcp"))
    if "tls" in report:
        print("tls:  %s %s" % (report.get("tls"), report.get("tls_version", "")))
    print("auth: %s" % report.get("auth", "-"))
    if isinstance(report.get("hub"), dict):
        print("hub:  ok, version %s, up %s"
              % (report["hub"].get("version"),
                 ago(report["hub"].get("uptime_seconds"))))
    if report.get("advice"):
        print("\n%s" % report["advice"])
        return 1
    return 0 if report.get("tcp") == "ok" else 1


def cmd_status(args):
    client = client_from(args)
    status = client.get("/v1/status")

    rows = []
    for agent in status["agents"]:
        rows.append([
            agent["name"],
            ",".join(agent["roles"]),
            agent["state"] + (" (draining)" if agent.get("draining") else ""),
            agent["slots"],
            ago(agent["last_seen_ago"]),
            (agent.get("meta") or {}).get("cpus", "-"),
            "%sGB" % (agent.get("meta") or {}).get("disk_free_gb", "-"),
        ])
    print("SERVERS")
    print(table(rows, ["name", "roles", "state", "slots", "seen", "cpu", "free"]))

    role_rows = []
    for role, stats in sorted(status["roles"].items()):
        role_rows.append([
            role, stats["queued"], stats["running"], stats["capacity"],
            stats["deficit"] or "", KNOWN_ROLES.get(role, ""),
        ])
    print("\nROLES")
    print(table(role_rows,
                ["role", "queued", "running", "slots", "short", "purpose"]))
    print("\nautoscale: %s via %s"
          % ("on" if status["autoscale"] else "off",
             status["driver"]["driver"]))
    return 0


def cmd_agents(args):
    client = client_from(args)
    agents = client.get("/v1/agents")["agents"]
    rows = [[a["id"], a["name"], ",".join(a["roles"]), a["state"],
             a["slots"], ago(a["last_seen_ago"])] for a in agents]
    print(table(rows, ["id", "name", "roles", "state", "slots", "seen"]))
    return 0


def _parse_payload(args):
    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    if args.payload:
        try:
            return json.loads(args.payload)
        except ValueError as exc:
            raise SystemExit("--payload is not valid JSON: %s" % exc)
    return {}


def cmd_submit(args):
    client = client_from(args)
    job = client.post("/v1/jobs", {
        "role": args.role,
        "kind": args.kind,
        "payload": _parse_payload(args),
        "priority": args.priority,
        "timeout_seconds": args.timeout,
    })
    print("queued %s  role=%s kind=%s" % (job["id"], job["role"], job["kind"]))
    if args.wait:
        return _wait(client, job["id"], args.wait_timeout)
    return 0


def cmd_jobs(args):
    client = client_from(args)
    jobs = client.get("/v1/jobs", params={
        "status": args.status, "role": args.role, "limit": args.limit,
    })["jobs"]
    rows = []
    for job in jobs:
        age = time.time() - job["created_at"]
        rows.append([job["id"], job["role"], job["kind"], job["status"],
                     "%d/%d" % (job["attempts"], job["max_attempts"]),
                     ago(age)])
    print(table(rows, ["id", "role", "kind", "status", "try", "age"]))
    return 0


def cmd_job(args):
    client = client_from(args)
    job = client.get("/v1/jobs/%s" % args.job_id)
    print("id:       %s" % job["id"])
    print("role:     %s    kind: %s" % (job["role"], job["kind"]))
    print("status:   %s (attempt %d/%d)"
          % (job["status"], job["attempts"], job["max_attempts"]))
    print("agent:    %s" % (job.get("agent_id") or "-"))
    if job.get("started_at"):
        end = job.get("finished_at") or time.time()
        print("runtime:  %s" % ago(end - job["started_at"]))
    if job.get("error"):
        print("error:    %s" % job["error"])
    if job.get("result"):
        print("result:   %s" % json.dumps(job["result"], indent=2)[:1500])
    artifacts = job.get("artifacts") or []
    if artifacts:
        print("\nARTIFACTS")
        print(table(
            [[a["id"], a["name"], "%.2f MB" % (a["size"] / 1048576.0)]
             for a in artifacts],
            ["artifact id", "name", "size"],
        ))
        print("\ndownload:  fleet download %s -o %s"
              % (artifacts[0]["id"], artifacts[0]["name"]))
    return 0


def _wait(client, job_id, timeout):
    """Poll a job to completion, printing status transitions only."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        job = client.get("/v1/jobs/%s" % job_id)
        if job["status"] != last:
            print("  %s" % job["status"])
            last = job["status"]
        if job["status"] in TERMINAL:
            if job["status"] == "done":
                for artifact in job.get("artifacts") or []:
                    print("  artifact %s  %s  %.2f MB"
                          % (artifact["id"], artifact["name"],
                             artifact["size"] / 1048576.0))
                return 0
            print("  error: %s" % job.get("error"))
            return 1
        time.sleep(3)
    print("  timed out after %ss (the job is still running)" % timeout)
    return 2


def cmd_watch(args):
    return _wait(client_from(args), args.job_id, args.wait_timeout)


def cmd_cancel(args):
    client = client_from(args)
    result = client.post("/v1/jobs/%s/cancel" % args.job_id)
    print("cancelled" if result.get("cancelled") else result.get("detail"))
    return 0 if result.get("cancelled") else 1


def cmd_download(args):
    client = client_from(args)
    data = client.get_bytes("/v1/artifacts/%s" % args.artifact_id)
    with open(args.output, "wb") as handle:
        handle.write(data)
    print("wrote %s (%.2f MB)" % (args.output, len(data) / 1048576.0))
    return 0


def cmd_scale(args):
    client = client_from(args)
    scale = client.get("/v1/scale")
    rows = []
    for role, stats in sorted(scale["roles"].items()):
        rows.append([role, stats["demand"], stats["capacity"],
                     stats["deficit"] or "", stats["surplus"] or ""])
    print("CAPACITY  (driver: %s, autoscale: %s)"
          % (scale["driver"]["driver"], "on" if scale["enabled"] else "off"))
    print(table(rows, ["role", "demand", "slots", "short", "idle"]))

    events = scale.get("recent_events") or []
    if events:
        print("\nRECENT SCALING DECISIONS")
        for event in events[:8]:
            print("  %s  %s/%s" % (
                time.strftime("%H:%M:%S", time.localtime(event["created_at"])),
                event["action"], event["role"]))
            print("    %s" % event["detail"])
    return 0


def cmd_drain(args):
    client = client_from(args)
    result = client.post("/v1/agents/%s/drain" % args.agent_id,
                         {"draining": not args.undo})
    print("%s: draining=%s" % (result["agent"], result["draining"]))
    return 0


def cmd_remove(args):
    client = client_from(args)
    client.delete("/v1/agents/%s" % args.agent_id)
    print("removed %s" % args.agent_id)
    return 0


def cmd_webinar(args):
    """Submit a whole webinar script as one job and follow it."""
    with open(args.script, "r", encoding="utf-8") as handle:
        script = json.load(handle)
    for field in ("sections",):
        if field not in script:
            raise SystemExit("script is missing %r" % field)
    client = client_from(args)
    job = client.post("/v1/jobs", {
        "role": args.role,
        "kind": "webinar",
        "payload": script,
        "priority": args.priority,
        "timeout_seconds": args.timeout,
    })
    print("queued webinar %s (%d sections) on role '%s'"
          % (job["id"], len(script["sections"]), args.role))
    return _wait(client, job["id"], args.wait_timeout)


def cmd_enroll_command(args):
    """Print the exact line to paste into a new box's console."""
    hub = args.hub or os.environ.get("FLEET_HUB", "https://YOUR-HUB")
    token = args.enroll_token or os.environ.get("FLEET_ENROLL_TOKEN", "<enroll-token>")
    print("Run this on the new server (as root):\n")
    print("  curl -fsSL %s/install.sh | bash -s -- \\" % hub.rstrip("/"))
    print("    --hub %s \\" % hub.rstrip("/"))
    print("    --enroll-token %s \\" % token)
    print("    --name %s \\" % args.name)
    print("    --roles %s --slots %d" % (args.roles, args.slots))
    print("\nOr, if you already copied the bundle across:\n")
    print("  sudo bash fleet/deploy/bootstrap_agent.sh --hub %s \\"
          % hub.rstrip("/"))
    print("    --enroll-token %s --name %s --roles %s --slots %d"
          % (token, args.name, args.roles, args.slots))
    return 0


# -- argument wiring -----------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="fleet", description="Drive the Cashbot render fleet")
    parser.add_argument("--hub", help="hub URL (or $FLEET_HUB)")
    parser.add_argument("--token", help="admin token (or $FLEET_TOKEN)")
    parser.add_argument("--insecure", action="store_true",
                        help="skip TLS verification (self-signed hub)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("preflight", help="diagnose connectivity to the hub"
                   ).set_defaults(func=cmd_preflight)
    sub.add_parser("status", help="servers and roles at a glance"
                   ).set_defaults(func=cmd_status)
    sub.add_parser("agents", help="list enrolled servers"
                   ).set_defaults(func=cmd_agents)
    sub.add_parser("scale", help="capacity and autoscaler decisions"
                   ).set_defaults(func=cmd_scale)

    submit = sub.add_parser("submit", help="queue one job")
    submit.add_argument("--role", required=True)
    submit.add_argument("--kind", required=True,
                        help="tts | render | webinar | shell")
    submit.add_argument("--payload", help="inline JSON")
    submit.add_argument("--payload-file")
    submit.add_argument("--priority", type=int, default=0)
    submit.add_argument("--timeout", type=int, default=3600)
    submit.add_argument("--wait", action="store_true")
    submit.add_argument("--wait-timeout", type=int, default=3600)
    submit.set_defaults(func=cmd_submit)

    jobs = sub.add_parser("jobs", help="list recent jobs")
    jobs.add_argument("--status")
    jobs.add_argument("--role")
    jobs.add_argument("--limit", type=int, default=25)
    jobs.set_defaults(func=cmd_jobs)

    job = sub.add_parser("job", help="show one job in detail")
    job.add_argument("job_id")
    job.set_defaults(func=cmd_job)

    watch = sub.add_parser("watch", help="follow a job to completion")
    watch.add_argument("job_id")
    watch.add_argument("--wait-timeout", type=int, default=3600)
    watch.set_defaults(func=cmd_watch)

    cancel = sub.add_parser("cancel", help="cancel a queued or running job")
    cancel.add_argument("job_id")
    cancel.set_defaults(func=cmd_cancel)

    download = sub.add_parser("download", help="fetch an artifact")
    download.add_argument("artifact_id")
    download.add_argument("-o", "--output", required=True)
    download.set_defaults(func=cmd_download)

    drain = sub.add_parser("drain", help="stop a server taking new work")
    drain.add_argument("agent_id")
    drain.add_argument("--undo", action="store_true")
    drain.set_defaults(func=cmd_drain)

    remove = sub.add_parser("remove", help="de-enroll a server")
    remove.add_argument("agent_id")
    remove.set_defaults(func=cmd_remove)

    webinar = sub.add_parser("webinar", help="render a webinar script")
    webinar.add_argument("script", help="path to a webinar script JSON file")
    webinar.add_argument("--role", default="webinar")
    webinar.add_argument("--priority", type=int, default=0)
    webinar.add_argument("--timeout", type=int, default=7200)
    webinar.add_argument("--wait-timeout", type=int, default=7200)
    webinar.set_defaults(func=cmd_webinar)

    enroll = sub.add_parser("enroll-command",
                            help="print the install line for a new box")
    enroll.add_argument("--name", required=True)
    enroll.add_argument("--roles", required=True)
    enroll.add_argument("--slots", type=int, default=1)
    enroll.add_argument("--enroll-token")
    enroll.set_defaults(func=cmd_enroll_command)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Unauthorized:
        print("Rejected by the hub. Check FLEET_TOKEN is the admin token.",
              file=sys.stderr)
        return 1
    except FleetError as exc:
        print("Hub error: %s" % exc, file=sys.stderr)
        return 1
    except ValueError as exc:
        print("%s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
