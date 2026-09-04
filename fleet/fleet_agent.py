#!/usr/bin/env python3
"""Fleet agent -- runs on each worker box and pulls work from the hub.

It only ever makes *outbound* HTTPS connections, so the box needs no open
ports, no public IP, no SSH exposure, and works fine behind home NAT. That is
what makes a machine on your own local network usable from the Claude app.

    python3 fleet_agent.py --hub https://hub.example.com \
        --enroll-token <token> --name video-01 --roles video --slots 2

State (agent id and token) is saved after enrolment, so restarts rejoin the
same identity instead of piling up duplicate agents.
"""

import argparse
import json
import os
import platform
import shutil
import signal
import socket
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fleetlib.client import FleetClient, FleetError, Unauthorized   # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fleet import handlers                                          # noqa: E402
from fleet.handlers.common import HandlerError                      # noqa: E402

VERSION = "1.0.0"
HEARTBEAT_INTERVAL = 30


def log(message):
    print("[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message), flush=True)


def stamp_result(result, worker, seconds):
    """Attach fleet metadata to a handler's result without overwriting it.

    The metadata keys are namespaced deliberately. An earlier version stamped
    "duration_seconds", which the render handler already uses for the length of
    the rendered video -- so the reported video length silently became the
    job's wall-clock runtime instead.
    """
    stamped = dict(result) if isinstance(result, dict) else {"result": result}
    stamped["job_seconds"] = round(seconds, 2)
    stamped["worker"] = worker
    return stamped


class JobContext:
    """What a handler is given: a private directory and a way to publish files."""

    def __init__(self, agent, job):
        self.agent = agent
        self.job = job
        self.workdir = os.path.join(agent.work_root, job["id"])
        os.makedirs(self.workdir, exist_ok=True)
        self.allow_shell = agent.allow_shell
        self.artifacts = []

    def log(self, message):
        log("  [%s] %s" % (self.job["id"][:12], message))

    def fetch(self, spec):
        """Resolve a job input into a real local file path.

        Accepts a local path, an http(s) URL, a hub artifact reference, or
        inline base64 -- so a job can carry its own small inputs without any
        shared filesystem between the hub and the workers.
        """
        if spec is None:
            raise HandlerError("job referenced an input that is null")
        if isinstance(spec, str):
            if spec.startswith(("http://", "https://")):
                return self._download(spec)
            if os.path.isabs(spec) and os.path.exists(spec):
                return spec
            local = os.path.join(self.workdir, spec)
            if os.path.exists(local):
                return local
            raise HandlerError(
                "input %r not found on this worker (looked in %s)"
                % (spec, self.workdir)
            )
        if isinstance(spec, dict):
            if spec.get("url"):
                return self._download(spec["url"])
            if spec.get("artifact_id"):
                return self._download_artifact(spec["artifact_id"],
                                               spec.get("name"))
            if spec.get("inline_base64"):
                import base64
                name = spec.get("name") or "input.bin"
                path = os.path.join(self.workdir, os.path.basename(name))
                with open(path, "wb") as handle:
                    handle.write(base64.b64decode(spec["inline_base64"]))
                return path
        raise HandlerError("cannot interpret job input: %r" % (spec,))

    def _download(self, url):
        parsed = urllib.parse.urlsplit(url)
        name = os.path.basename(parsed.path) or "download.bin"
        path = os.path.join(self.workdir, name)
        self.log("fetching %s" % url)
        client = FleetClient(
            "%s://%s" % (parsed.scheme, parsed.netloc), timeout=300,
            insecure=self.agent.insecure, ca_file=self.agent.ca_file,
        )
        query = ("?" + parsed.query) if parsed.query else ""
        raw = client.get_bytes((parsed.path or "/") + query)
        with open(path, "wb") as handle:
            handle.write(raw)
        return path

    def _download_artifact(self, artifact_id, name=None):
        path = os.path.join(self.workdir, name or (artifact_id + ".bin"))
        self.log("fetching artifact %s" % artifact_id)
        data = self.agent.client.get_bytes("/v1/artifacts/%s" % artifact_id)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def artifact(self, path):
        """Upload a produced file to the hub and record it on the job."""
        if not os.path.exists(path):
            raise HandlerError("handler published a file that does not exist: %s"
                               % path)
        name = os.path.basename(path)
        size = os.path.getsize(path)
        self.log("uploading %s (%.1f MB)" % (name, size / 1048576.0))
        with open(path, "rb") as handle:
            data = handle.read()
        response = self.agent.client.post_bytes(
            "/v1/jobs/%s/artifacts" % self.job["id"], data,
            headers={"X-Artifact-Name": name}, timeout=900,
        )
        self.artifacts.append(response)
        return response

    def cleanup(self, keep=False):
        if keep:
            return
        shutil.rmtree(self.workdir, ignore_errors=True)


class Agent:
    def __init__(self, args):
        self.hub_url = args.hub.rstrip("/")
        self.name = args.name or socket.gethostname()
        self.roles = [r.strip().lower() for r in args.roles.split(",") if r.strip()]
        self.slots = max(1, args.slots)
        self.state_path = os.path.abspath(args.state)
        self.work_root = os.path.abspath(args.work_dir)
        self.allow_shell = args.allow_shell
        self.keep_workdirs = args.keep_workdirs
        self.insecure = args.insecure
        self.ca_file = args.ca_file
        self.enroll_token = args.enroll_token or os.environ.get("FLEET_ENROLL_TOKEN")

        os.makedirs(self.work_root, exist_ok=True)
        self.agent_id = None
        self.token = None
        self.client = None
        self._stop = threading.Event()
        self._active = threading.Semaphore(self.slots)
        self._running = 0
        self._lock = threading.Lock()

    # -- identity --------------------------------------------------------

    def load_state(self):
        if not os.path.exists(self.state_path):
            return False
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (ValueError, OSError):
            log("state file at %s is unreadable; re-enrolling" % self.state_path)
            return False
        if state.get("hub") != self.hub_url:
            log("state file belongs to a different hub (%s); re-enrolling"
                % state.get("hub"))
            return False
        self.agent_id = state.get("agent_id")
        self.token = state.get("agent_token")
        return bool(self.agent_id and self.token)

    def save_state(self):
        directory = os.path.dirname(self.state_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump({
                "hub": self.hub_url,
                "agent_id": self.agent_id,
                "agent_token": self.token,
                "name": self.name,
                "roles": self.roles,
            }, handle, indent=2)
        os.chmod(self.state_path, 0o600)

    def enroll(self):
        if not self.enroll_token:
            raise SystemExit(
                "This agent has no identity yet and no enrollment token was "
                "given. Pass --enroll-token or set FLEET_ENROLL_TOKEN."
            )
        if not self.roles:
            raise SystemExit(
                "Specify at least one role, e.g. --roles video or "
                "--roles audio,webinar"
            )
        client = FleetClient(self.hub_url, token=self.enroll_token,
                             insecure=self.insecure, ca_file=self.ca_file)
        log("enrolling with %s as %s (roles: %s)"
            % (self.hub_url, self.name, ",".join(self.roles)))
        response = client.post("/v1/agents/enroll", {
            "name": self.name,
            "roles": self.roles,
            "slots": self.slots,
            "version": VERSION,
            "meta": self.machine_info(),
        })
        self.agent_id = response["agent_id"]
        self.token = response["agent_token"]
        self.save_state()
        log("enrolled as %s" % self.agent_id)

    def machine_info(self):
        info = {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpus": os.cpu_count(),
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "piper": shutil.which("piper") is not None,
            "handlers": sorted(handlers.REGISTRY),
        }
        try:
            usage = shutil.disk_usage(self.work_root)
            info["disk_free_gb"] = round(usage.free / 1073741824.0, 1)
        except OSError:
            pass
        return info

    # -- main loop -------------------------------------------------------

    def start(self):
        if not self.load_state():
            self.enroll()
        self.client = FleetClient(
            self.hub_url, token=self.token, agent_id=self.agent_id,
            insecure=self.insecure, ca_file=self.ca_file,
        )
        report = self.client.preflight()
        if report.get("tcp") != "ok":
            log("cannot reach the hub: %s" % report.get("advice", report))
            return 1

        threading.Thread(target=self._heartbeat_loop, name="heartbeat",
                         daemon=True).start()
        log("agent %s online: roles=%s slots=%d handlers=%s"
            % (self.name, ",".join(self.roles), self.slots,
               ",".join(sorted(handlers.REGISTRY))))
        self._claim_loop()
        return 0

    def stop(self, *_):
        log("stop requested; finishing in-flight jobs")
        self._stop.set()

    def _heartbeat_loop(self):
        while not self._stop.wait(HEARTBEAT_INTERVAL):
            try:
                self.client.post("/v1/agents/%s/heartbeat" % self.agent_id,
                                 {"version": VERSION, "meta": self.machine_info()})
            except Unauthorized:
                log("hub rejected our token -- this agent was removed. Delete "
                    "%s and restart to re-enroll." % self.state_path)
                self._stop.set()
            except FleetError as exc:
                log("heartbeat failed (will retry): %s" % exc)
            except Exception as exc:
                log("heartbeat error: %r" % exc)

    def _claim_loop(self):
        backoff = 1
        while not self._stop.is_set():
            # Block until a slot frees up, so we never claim more work than we
            # can actually run in parallel.
            if not self._active.acquire(timeout=1):
                continue
            if self._stop.is_set():
                self._active.release()
                break
            try:
                job = self.client.post("/v1/jobs/claim", {},
                                       timeout=self.client.timeout + 60)
                backoff = 1
            except (socket.timeout, TimeoutError):
                self._active.release()
                continue
            except Unauthorized:
                self._active.release()
                log("hub rejected our token; stopping")
                break
            except FleetError as exc:
                self._active.release()
                log("claim failed: %s (retrying in %ds)" % (exc, backoff))
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 60)
                continue

            if not job or not job.get("id"):
                self._active.release()
                continue

            threading.Thread(target=self._run_job, args=(job,),
                             name="job-" + job["id"][:8], daemon=False).start()

        log("agent stopped")

    def _run_job(self, job):
        started = time.time()
        with self._lock:
            self._running += 1
        log("running %s kind=%s role=%s" % (job["id"], job["kind"], job["role"]))
        ctx = JobContext(self, job)
        try:
            handler = handlers.get(job["kind"])
            result = handler(job.get("payload") or {}, ctx)
            result = stamp_result(result, self.name, time.time() - started)
            self.client.post("/v1/jobs/%s/complete" % job["id"], {"result": result})
            log("completed %s in %.1fs" % (job["id"], time.time() - started))
        except HandlerError as exc:
            # A handler error is a real, explainable failure -- do not retry it
            # on another box, it will fail there for the same reason.
            log("job %s failed: %s" % (job["id"], exc))
            self._report_failure(job["id"], str(exc), retry=False)
        except Exception as exc:
            log("job %s crashed: %r" % (job["id"], exc))
            self._report_failure(job["id"], "%s: %s" % (type(exc).__name__, exc),
                                 retry=True)
        finally:
            ctx.cleanup(keep=self.keep_workdirs)
            with self._lock:
                self._running -= 1
            self._active.release()

    def _report_failure(self, job_id, error, retry):
        try:
            self.client.post("/v1/jobs/%s/fail" % job_id,
                             {"error": error, "retry": retry})
        except FleetError as exc:
            # The job will be reclaimed by lease expiry, so this is not fatal.
            log("could not report failure for %s: %s" % (job_id, exc))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fleet worker agent")
    parser.add_argument("--hub", default=os.environ.get("FLEET_HUB"),
                        required=not os.environ.get("FLEET_HUB"))
    parser.add_argument("--name", default=os.environ.get("FLEET_AGENT_NAME"))
    parser.add_argument("--roles", default=os.environ.get("FLEET_ROLES", ""),
                        help="comma separated, e.g. video or audio,webinar")
    parser.add_argument("--slots", type=int,
                        default=int(os.environ.get("FLEET_SLOTS", "1")),
                        help="how many jobs this box runs at once")
    parser.add_argument("--enroll-token")
    parser.add_argument("--state", default=os.environ.get(
        "FLEET_STATE", "./fleet-agent.json"))
    parser.add_argument("--work-dir", default=os.environ.get(
        "FLEET_WORK_DIR", "./fleet-work"))
    parser.add_argument("--allow-shell", action="store_true",
                        help="permit remote shell jobs on this machine")
    parser.add_argument("--keep-workdirs", action="store_true",
                        help="do not delete job directories (for debugging)")
    parser.add_argument("--ca-file", default=os.environ.get("FLEET_CA_FILE"))
    parser.add_argument("--insecure", action="store_true",
                        help="skip TLS verification (self-signed hub on a LAN)")
    args = parser.parse_args(argv)

    agent = Agent(args)
    signal.signal(signal.SIGTERM, agent.stop)
    signal.signal(signal.SIGINT, agent.stop)
    return agent.start()


if __name__ == "__main__":
    sys.exit(main())
