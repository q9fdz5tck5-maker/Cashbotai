#!/usr/bin/env python3
"""Let Claude drive the fleet.

Claude Code starts this file as a subprocess and talks to it over the pipe.
You never run it yourself; you point Claude at it once and then say things
like "make me a two minute video about X" or "which of my computers are on?".

Point it at your hub with two variables:

    FLEET_HUB=https://hub.example.com
    FLEET_TOKEN=<your private code>

To register it with Claude Code, from the folder you unpacked:

    claude mcp add fleet -- python3 fleet_mcp.py

or drop the .mcp.json that ships beside this file into the project folder,
which does the same thing without a command.

Transport is stdio with newline-delimited JSON, which is what the MCP spec
calls for. Anything this program wants to say to a human goes to stderr --
stdout carries protocol only, and one stray print there corrupts the session.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fleetlib import mcp                                        # noqa: E402


def note(message):
    """Human-facing output. Never stdout: that channel is the protocol."""
    print(message, file=sys.stderr, flush=True)


def serve(stdin=None, stdout=None, ctx=None):
    """Read newline-delimited JSON-RPC from stdin, answer on stdout."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    ctx = ctx if ctx is not None else mcp.build_context()

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError as exc:
            _write(stdout, {"jsonrpc": "2.0", "id": None,
                            "error": {"code": mcp.PARSE_ERROR,
                                      "message": "invalid JSON: %s" % exc}})
            continue

        # A batch is a JSON array. Notifications inside it still produce no
        # reply, so a batch of only notifications is answered with silence.
        if isinstance(message, list):
            replies = [r for r in (mcp.dispatch(m, ctx) for m in message)
                       if r is not None]
            if replies:
                _write(stdout, replies)
            continue

        response = mcp.dispatch(message, ctx)
        if response is not None:
            _write(stdout, response)
    return 0


def _write(stdout, payload):
    stdout.write(json.dumps(payload) + "\n")
    stdout.flush()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        note(__doc__.strip())
        return 0

    if "--self-test" in argv:
        return _self_test()

    hub = os.environ.get("FLEET_HUB")
    if not hub:
        note("fleet-mcp: FLEET_HUB is not set, so no tool can reach a hub.")
        note("           Set FLEET_HUB and FLEET_TOKEN, then start me again.")
    else:
        note("fleet-mcp: ready, talking to %s" % hub)
    try:
        return serve()
    except (KeyboardInterrupt, BrokenPipeError):
        return 0


def _self_test():
    """Prove the protocol side works without a hub, a network, or Claude.

    This is the thing to run when Claude says it cannot start the server: if
    this prints OK, the fault is in how Claude was pointed at the file, not in
    the file.
    """
    import io
    script = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "self-test", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    stdin = io.StringIO("\n".join(json.dumps(m) for m in script) + "\n")
    stdout = io.StringIO()
    serve(stdin=stdin, stdout=stdout, ctx=mcp.build_context(hub_url=None))
    replies = [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]
    if len(replies) != 2:
        note("FAILED: expected 2 replies (the notification must get none), "
             "got %d" % len(replies))
        return 1
    tools = replies[1]["result"]["tools"]
    note("OK: protocol %s, %d tools: %s"
         % (replies[0]["result"]["protocolVersion"], len(tools),
            ", ".join(t["name"] for t in tools)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
