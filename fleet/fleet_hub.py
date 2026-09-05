#!/usr/bin/env python3
"""Fleet hub -- the control plane every agent and every client talks to.

Run this on one machine with a public address on port 443. Agents poll it for
work; you submit work to it from the Claude app. Nothing ever connects *into*
an agent, which is why this design works from a phone and needs no SSH.

    python3 fleet_hub.py --port 443 --cert /etc/fleet/cert.pem \
        --key /etc/fleet/key.pem --data /var/lib/fleet

Standard library only.
"""

import argparse
import hashlib
import json
import os
import secrets
import socketserver
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fleetlib import mcp as mcp_server            # noqa: E402
from fleetlib import models                      # noqa: E402
from fleetlib.autoscale import Autoscaler        # noqa: E402
from fleetlib.models import Job                  # noqa: E402
from fleetlib.roles import normalise_roles       # noqa: E402
from fleetlib.store import Store                 # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fleet import drivers                        # noqa: E402

VERSION = "1.0.0"
MAX_BODY = 64 * 1024 * 1024          # 64 MB cap on any single request body
CLAIM_POLL_INTERVAL = 1.0


class HubConfig:
    def __init__(self, args):
        self.data_dir = os.path.abspath(args.data)
        self.db_path = os.path.join(self.data_dir, "fleet.db")
        self.artifact_dir = os.path.join(self.data_dir, "artifacts")
        os.makedirs(self.artifact_dir, exist_ok=True)

        self.admin_token = args.admin_token or os.environ.get("FLEET_ADMIN_TOKEN")
        self.enroll_token = args.enroll_token or os.environ.get("FLEET_ENROLL_TOKEN")
        self.driver_name = args.driver
        self.driver_config = json.loads(args.driver_config) if args.driver_config else {}
        self.autoscale = not args.no_autoscale
        self.claim_wait = args.claim_wait

        # Generating a token and printing it once is friendlier than refusing to
        # boot, but it must be loud -- a hub with a token nobody wrote down is
        # a hub you have to restart.
        self._generated = []
        if not self.admin_token:
            self.admin_token = models.new_token()
            self._generated.append(("FLEET_ADMIN_TOKEN", self.admin_token))
        if not self.enroll_token:
            self.enroll_token = models.new_token()
            self._generated.append(("FLEET_ENROLL_TOKEN", self.enroll_token))

    def announce_generated(self):
        if not self._generated:
            return
        print("\n" + "=" * 68)
        print("  No tokens were supplied, so these were generated for you.")
        print("  Save them now -- they are not written to disk.")
        print("=" * 68)
        for name, value in self._generated:
            print("  %s=%s" % (name, value))
        print("=" * 68 + "\n", flush=True)


class HubState:
    """Everything the request handler needs, assembled once at startup."""

    def __init__(self, config):
        self.config = config
        self.store = Store(config.db_path)
        self.driver = drivers.load(config.driver_name, config.driver_config)
        self.autoscaler = Autoscaler(
            self.store, self.driver, enabled=config.autoscale
        )
        self.started_at = time.time()
        self._stop = threading.Event()
        self._maintenance = None
        # Filled in by make_server once the socket exists. The MCP tools reach
        # the fleet the same way any other client does -- over HTTP with the
        # admin token -- so there is exactly one code path to the hub's API and
        # no second, privileged one that could drift out of step with it.
        self.self_url = None
        self._mcp_context = None
        self._mcp_lock = threading.Lock()

    def mcp_context(self):
        with self._mcp_lock:
            if self._mcp_context is None:
                self._mcp_context = mcp_server.build_context(
                    hub_url=self.self_url,
                    token=self.config.admin_token,
                    # The enrolment token lets `add_computer` hand back a line
                    # that is ready to paste. Whoever reached this endpoint
                    # already presented the admin token, which can do strictly
                    # more than enrol a machine.
                    enroll_token=self.config.enroll_token,
                )
            return self._mcp_context

    def start_maintenance(self):
        self._maintenance = threading.Thread(
            target=self._maintenance_loop, name="fleet-maintenance", daemon=True
        )
        self._maintenance.start()

    def stop(self):
        self._stop.set()

    def _maintenance_loop(self):
        """Reclaim dead leases and run the autoscaler on a slow tick."""
        while not self._stop.wait(15):
            try:
                reclaimed = self.store.reclaim_expired()
                if reclaimed:
                    log("reclaimed %d job(s) from dead agents" % reclaimed)
                for decision in self.autoscaler.evaluate():
                    log("autoscale %s/%s fulfilled=%s :: %s" % (
                        decision.action, decision.role, decision.fulfilled,
                        decision.detail,
                    ))
            except Exception as exc:            # keep the loop alive
                log("maintenance error: %r" % exc)


def log(message):
    print("[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message), flush=True)


class HubHandler(BaseHTTPRequestHandler):
    server_version = "fleet-hub/" + VERSION
    protocol_version = "HTTP/1.1"
    state = None                                 # injected by make_server

    # -- helpers ---------------------------------------------------------

    def log_message(self, fmt, *args):
        # BaseHTTPRequestHandler logs to stderr per request; route it through
        # our own formatter so hub output is one consistent stream.
        log("%s %s" % (self.address_string(), fmt % args))

    # Statuses that must not carry a response body (RFC 9110). Writing one
    # anyway leaves the bytes in the socket, where the client reads them as the
    # start of the next response -- a 204 with a "{}" body corrupted the very
    # next request on a keep-alive connection.
    BODYLESS_STATUSES = (204, 304)

    def _send(self, status, payload, raw=False, content_type="application/json"):
        if status in self.BODYLESS_STATUSES:
            self.send_response(status)
            self.send_header("X-Fleet-Version", VERSION)
            self.end_headers()
            return

        if raw:
            body = payload
        else:
            body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Fleet-Version", VERSION)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _no_content(self):
        """202 with a genuinely empty body.

        202 is *not* in BODYLESS_STATUSES and must not be: unlike 204 and 304
        it is allowed to carry a body, so a client that gets no Content-Length
        reads until the connection closes -- which on a keep-alive connection
        means it hangs until the socket times out. The length has to be stated.
        """
        self._send(202, b"", raw=True)

    def _error(self, status, message):
        self._send(status, {"error": message})

    def _consume_body(self):
        """Read the whole request body once, before routing.

        Doing this up front rather than inside each endpoint is what keeps
        HTTP/1.1 keep-alive correct: an endpoint that forgot to read its body
        used to leave those bytes in the socket, where the server then parsed
        them as the start of the next request and answered 400.
        """
        length = int(self.headers.get("Content-Length") or 0)
        if length < 0:
            raise ValueError("negative Content-Length")
        if length > MAX_BODY:
            raise ValueError("body larger than %d bytes" % MAX_BODY)
        self._raw_body = self.rfile.read(length) if length else b""

    def _read_body(self):
        return getattr(self, "_raw_body", b"")

    def _read_json(self):
        raw = self._read_body()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _bearer(self):
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[7:].strip()
        return None

    def _require_admin(self):
        token = self._bearer()
        if not token or not secrets.compare_digest(
            token, self.state.config.admin_token
        ):
            self._error(401, "admin token required")
            return False
        return True

    def _require_agent(self):
        """Authenticate an agent from its id header plus bearer token."""
        agent_id = self.headers.get("X-Fleet-Agent", "")
        token = self._bearer()
        if not agent_id or not token:
            self._error(401, "agent id and token required")
            return None
        agent = self.state.store.authenticate_agent(agent_id, token)
        if agent is None:
            self._error(401, "unknown agent or bad token")
            return None
        return agent

    # -- routing ---------------------------------------------------------

    def do_GET(self):
        try:
            self._route_get()
        except Exception as exc:
            log("GET %s failed: %r" % (self.path, exc))
            self._error(500, "internal error: %s" % exc)

    def do_DELETE(self):
        try:
            self._route_delete()
        except Exception as exc:
            log("DELETE %s failed: %r" % (self.path, exc))
            self._error(500, "internal error: %s" % exc)

    def do_POST(self):
        try:
            self._consume_body()
            self._route_post()
        except ValueError as exc:
            self._error(400, str(exc))
        except Exception as exc:
            log("POST %s failed: %r" % (self.path, exc))
            self._error(500, "internal error: %s" % exc)

    def _path_parts(self):
        path = self.path.split("?", 1)[0].strip("/")
        return path.split("/") if path else []

    def _query(self):
        if "?" not in self.path:
            return {}
        import urllib.parse
        return dict(urllib.parse.parse_qsl(self.path.split("?", 1)[1]))

    # -- GET -------------------------------------------------------------

    def _route_get(self):
        parts = self._path_parts()
        store = self.state.store

        if parts == ["v1", "health"]:
            return self._send(200, {
                "ok": True,
                "version": VERSION,
                "uptime_seconds": round(time.time() - self.state.started_at, 1),
            })

        if parts == ["mcp"]:
            # The Streamable HTTP transport lets a server decline the optional
            # server-to-client stream, and says to answer 405 when it does.
            # This hub has nothing to push, so every exchange is one POST.
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None

        if parts == ["v1", "agents"]:
            if not self._require_admin():
                return None
            return self._send(200, {
                "agents": [a.to_dict() for a in store.list_agents()]
            })

        if parts == ["v1", "jobs"]:
            if not self._require_admin():
                return None
            query = self._query()
            jobs = store.list_jobs(
                status=query.get("status"),
                role=query.get("role"),
                limit=min(int(query.get("limit", 50)), 500),
            )
            return self._send(200, {"jobs": [j.to_dict() for j in jobs]})

        if len(parts) == 3 and parts[:2] == ["v1", "jobs"]:
            if not self._require_admin():
                return None
            job = store.get_job(parts[2])
            if job is None:
                return self._error(404, "no such job")
            data = job.to_dict()
            data["artifacts"] = store.list_artifacts(job.id)
            return self._send(200, data)

        if len(parts) == 3 and parts[:2] == ["v1", "artifacts"]:
            if not self._require_admin():
                return None
            return self._download_artifact(parts[2])

        if parts == ["v1", "scale"]:
            if not self._require_admin():
                return None
            snapshot = self.state.autoscaler.snapshot()
            return self._send(200, {
                "enabled": self.state.autoscaler.enabled,
                "driver": self.state.driver.describe(),
                "roles": snapshot["roles"],
                "recent_events": store.recent_scale_events(),
            })

        if parts == ["v1", "status"]:
            if not self._require_admin():
                return None
            snapshot = self.state.autoscaler.snapshot()
            return self._send(200, {
                "version": VERSION,
                "uptime_seconds": round(time.time() - self.state.started_at, 1),
                "agents": snapshot["agents"],
                "roles": snapshot["roles"],
                "driver": self.state.driver.describe(),
                "autoscale": self.state.autoscaler.enabled,
            })

        return self._error(404, "no such endpoint: %s" % self.path)

    def _download_artifact(self, artifact_id):
        record = self.state.store.get_artifact(artifact_id)
        if record is None:
            return self._error(404, "no such artifact")
        path = record["path"]
        if not os.path.exists(path):
            return self._error(410, "artifact record exists but the file is gone")
        with open(path, "rb") as handle:
            body = handle.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Content-Disposition",
            'attachment; filename="%s"' % os.path.basename(record["name"]),
        )
        self.end_headers()
        self.wfile.write(body)
        return None

    # -- DELETE ----------------------------------------------------------

    def _route_delete(self):
        parts = self._path_parts()
        if len(parts) == 3 and parts[:2] == ["v1", "agents"]:
            if not self._require_admin():
                return None
            self.state.store.remove_agent(parts[2])
            return self._send(200, {"removed": parts[2]})
        return self._error(404, "no such endpoint: %s" % self.path)

    # -- POST ------------------------------------------------------------

    def _route_post(self):
        parts = self._path_parts()
        store = self.state.store

        if parts == ["mcp"]:
            return self._mcp()

        if parts == ["v1", "agents", "enroll"]:
            return self._enroll()

        if len(parts) == 4 and parts[:2] == ["v1", "agents"] and parts[3] == "heartbeat":
            agent = self._require_agent()
            if agent is None:
                return None
            if agent.id != parts[2]:
                return self._error(403, "token does not match that agent")
            body = self._read_json()
            store.heartbeat(agent.id, body.get("version"), body.get("meta"))
            return self._send(200, {"ok": True, "draining": agent.draining})

        if len(parts) == 4 and parts[:2] == ["v1", "agents"] and parts[3] == "drain":
            if not self._require_admin():
                return None
            body = self._read_json()
            store.set_draining(parts[2], bool(body.get("draining", True)))
            return self._send(200, {"agent": parts[2],
                                    "draining": bool(body.get("draining", True))})

        if parts == ["v1", "jobs"]:
            if not self._require_admin():
                return None
            return self._submit_job()

        if parts == ["v1", "jobs", "claim"]:
            agent = self._require_agent()
            if agent is None:
                return None
            return self._claim(agent)

        if len(parts) == 4 and parts[:2] == ["v1", "jobs"]:
            job_id, action = parts[2], parts[3]
            if action == "cancel":
                if not self._require_admin():
                    return None
                ok = store.cancel(job_id)
                return self._send(200 if ok else 409, {
                    "cancelled": ok,
                    "detail": None if ok else "job already finished",
                })
            agent = self._require_agent()
            if agent is None:
                return None
            if action == "complete":
                return self._complete(agent, job_id)
            if action == "fail":
                return self._fail(agent, job_id)
            if action == "artifacts":
                return self._upload_artifact(agent, job_id)

        return self._error(404, "no such endpoint: %s" % self.path)

    def _mcp(self):
        """Serve the Model Context Protocol over one HTTP POST.

        This is what lets the fleet be added to the Claude app as a connector,
        so a phone can drive the machines with nothing installed on it. The
        same tools are served over stdio by ``fleet_mcp.py``; both call
        ``fleetlib.mcp.dispatch``, so neither can grow a tool the other lacks.

        A notification carries no id and gets no response body -- 202 with an
        empty body is what the transport specifies, and answering one with a
        result makes a client wait for a reply to a message it never sent.
        """
        if not self._require_admin():
            return None
        try:
            message = json.loads(self._read_body().decode("utf-8") or "null")
        except ValueError as exc:
            return self._send(400, {
                "jsonrpc": "2.0", "id": None,
                "error": {"code": mcp_server.PARSE_ERROR,
                          "message": "invalid JSON: %s" % exc},
            })

        ctx = self.state.mcp_context()
        if isinstance(message, list):
            replies = [r for r in (mcp_server.dispatch(m, ctx) for m in message)
                       if r is not None]
            if not replies:
                return self._no_content()
            return self._send(200, replies)

        response = mcp_server.dispatch(message, ctx)
        if response is None:
            return self._no_content()
        return self._send(200, response)

    def _enroll(self):
        token = self._bearer()
        if not token or not secrets.compare_digest(
            token, self.state.config.enroll_token
        ):
            return self._error(401, "enrollment token required")
        body = self._read_json()
        name = (body.get("name") or "").strip()
        roles = normalise_roles(body.get("roles") or [])
        if not name:
            return self._error(400, "name is required")
        if not roles:
            return self._error(
                400, "at least one role is required (e.g. audio, video, webinar)"
            )
        agent, agent_token = self.state.store.enroll_agent(
            name, roles, slots=body.get("slots", 1),
            version=body.get("version", ""), meta=body.get("meta"),
        )
        log("enrolled agent %s (%s) roles=%s slots=%d"
            % (agent.name, agent.id, ",".join(roles), agent.slots))
        return self._send(201, {
            "agent_id": agent.id,
            "agent_token": agent_token,
            "name": agent.name,
            "roles": agent.roles,
            "slots": agent.slots,
        })

    def _submit_job(self):
        body = self._read_json()
        role = (body.get("role") or "").strip().lower()
        kind = (body.get("kind") or "").strip()
        if not role:
            return self._error(400, "role is required")
        if not kind:
            return self._error(400, "kind is required (e.g. tts, render, webinar)")
        job = Job(
            role=role,
            kind=kind,
            payload=body.get("payload") or {},
            priority=int(body.get("priority", 0)),
            max_attempts=int(body.get("max_attempts", 3)),
            timeout_seconds=int(body.get("timeout_seconds", 3600)),
        )
        self.state.store.enqueue(job)
        log("queued %s role=%s kind=%s" % (job.id, job.role, job.kind))
        return self._send(201, job.to_dict())

    def _claim(self, agent):
        """Long-poll: hold the request open until work appears or we time out.

        Returning 204 rather than an error on an empty queue keeps agent logs
        clean -- no work is the normal case, not a failure.
        """
        self.state.store.heartbeat(agent.id)
        deadline = time.time() + self.state.config.claim_wait
        while True:
            job = self.state.store.claim(agent)
            if job is not None:
                log("agent %s claimed %s (%s)" % (agent.name, job.id, job.kind))
                return self._send(200, job.to_dict())
            if time.time() >= deadline:
                return self._send(204, {})
            time.sleep(CLAIM_POLL_INTERVAL)

    def _owns(self, agent, job_id):
        job = self.state.store.get_job(job_id)
        if job is None:
            self._error(404, "no such job")
            return None
        if job.agent_id != agent.id:
            self._error(403, "job is assigned to a different agent")
            return None
        return job

    def _complete(self, agent, job_id):
        if self._owns(agent, job_id) is None:
            return None
        body = self._read_json()
        self.state.store.complete(job_id, body.get("result"))
        log("job %s completed by %s" % (job_id, agent.name))
        return self._send(200, {"ok": True, "job_id": job_id})

    def _fail(self, agent, job_id):
        if self._owns(agent, job_id) is None:
            return None
        body = self._read_json()
        state = self.state.store.fail(
            job_id, body.get("error", "unspecified"),
            retry=bool(body.get("retry", True)),
        )
        log("job %s failed on %s -> %s" % (job_id, agent.name, state))
        return self._send(200, {"ok": True, "job_id": job_id, "state": state})

    def _upload_artifact(self, agent, job_id):
        if self._owns(agent, job_id) is None:
            return None
        name = self.headers.get("X-Artifact-Name") or "artifact.bin"
        # Never let a worker-supplied name escape the artifact directory.
        safe_name = os.path.basename(name).replace("..", "_") or "artifact.bin"
        data = self._read_body()
        job_dir = os.path.join(self.state.config.artifact_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        path = os.path.join(job_dir, safe_name)
        with open(path, "wb") as handle:
            handle.write(data)
        digest = hashlib.sha256(data).hexdigest()
        artifact_id = self.state.store.add_artifact(
            job_id, safe_name, path, len(data), digest
        )
        log("artifact %s (%s, %d bytes) for %s" % (artifact_id, safe_name,
                                                   len(data), job_id))
        return self._send(201, {
            "artifact_id": artifact_id,
            "name": safe_name,
            "size": len(data),
            "sha256": digest,
        })


def make_server(config, bind, port):
    state = HubState(config)

    handler = type("BoundHubHandler", (HubHandler,), {"state": state})
    # allow_reuse_address stops a restart from failing on TIME_WAIT sockets.
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((bind, port), handler)
    httpd.daemon_threads = True
    # Loopback, not the public name: the MCP tools must reach this process
    # whether or not DNS resolves yet and whether or not a TLS terminator sits
    # in front of it.
    state.self_url = "http://127.0.0.1:%d" % httpd.server_address[1]
    return httpd, state


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fleet hub control plane")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--data", default="./fleet-data",
                        help="directory for the database and artifacts")
    parser.add_argument("--cert", help="TLS certificate (PEM)")
    parser.add_argument("--key", help="TLS private key (PEM)")
    parser.add_argument("--admin-token", help="defaults to $FLEET_ADMIN_TOKEN")
    parser.add_argument("--enroll-token", help="defaults to $FLEET_ENROLL_TOKEN")
    parser.add_argument("--driver", default="manual",
                        help="capacity driver: " + ", ".join(drivers.available()))
    parser.add_argument("--driver-config", help="driver config as a JSON object")
    parser.add_argument("--no-autoscale", action="store_true")
    parser.add_argument("--claim-wait", type=int, default=25,
                        help="seconds to hold a claim long-poll open")
    args = parser.parse_args(argv)

    config = HubConfig(args)
    httpd, state = make_server(config, args.bind, args.port)

    scheme = "http"
    if args.cert and args.key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.cert, args.key)
        # TLS 1.2 floor: anything older has no business terminating job tokens.
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    elif args.port == 443:
        log("WARNING: serving plain HTTP on 443. Put a TLS terminator in front "
            "or pass --cert/--key; tokens are sent in every request.")

    config.announce_generated()
    state.start_maintenance()
    log("fleet hub %s listening on %s://%s:%d (driver=%s, autoscale=%s)"
        % (VERSION, scheme, args.bind, args.port, args.driver,
           not args.no_autoscale))
    log("data dir: %s" % config.data_dir)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("shutting down")
    finally:
        state.stop()
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
