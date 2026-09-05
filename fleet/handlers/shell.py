"""Run a shell command on a worker.

Disabled unless the agent is started with ``--allow-shell``. It is the most
useful handler for ad-hoc work and obviously the most dangerous one: anybody
holding the hub admin token can run arbitrary code on every box that enables
it. Leave it off on machines that hold credentials.
"""

import os

from .common import HandlerError, run_command, safe_join


def run(payload, ctx):
    if not getattr(ctx, "allow_shell", False):
        raise HandlerError(
            "This worker refuses shell jobs. Start its agent with "
            "--allow-shell if you intend to allow remote command execution."
        )
    command = payload.get("command")
    if not command:
        raise HandlerError("shell job needs a 'command'")

    ctx.log("shell: %s" % command)
    output = run_command(
        ["/bin/sh", "-c", command],
        cwd=ctx.workdir,
        timeout=int(payload.get("timeout", 1800)),
    )

    for name in payload.get("collect") or []:
        path = safe_join(ctx.workdir, name)
        if os.path.exists(path):
            ctx.artifact(path)
        else:
            ctx.log("collect: %s was not produced" % name)

    tail = output.strip().splitlines()[-200:]
    return {"output": "\n".join(tail), "lines": len(output.splitlines())}
