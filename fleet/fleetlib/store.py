"""SQLite persistence for the hub.

SQLite rather than Postgres on purpose: the whole fleet has to survive being
zipped up and handed to someone else, and a single file that travels with the
bundle does that. It comfortably handles the job rates a render fleet produces.
"""

import hashlib
import json
import os
import sqlite3
import threading

from . import models
from .models import Agent, Job
from .roles import normalise_roles

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    roles        TEXT NOT NULL,
    slots        INTEGER NOT NULL DEFAULT 1,
    token_hash   TEXT NOT NULL,
    enrolled_at  REAL NOT NULL,
    last_seen    REAL NOT NULL,
    version      TEXT DEFAULT '',
    meta         TEXT DEFAULT '{}',
    draining     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    role             TEXT NOT NULL,
    kind             TEXT NOT NULL,
    payload          TEXT NOT NULL DEFAULT '{}',
    status           TEXT NOT NULL,
    priority         INTEGER NOT NULL DEFAULT 0,
    created_at       REAL NOT NULL,
    started_at       REAL,
    finished_at      REAL,
    agent_id         TEXT,
    attempts         INTEGER NOT NULL DEFAULT 0,
    max_attempts     INTEGER NOT NULL DEFAULT 3,
    error            TEXT,
    result           TEXT,
    timeout_seconds  INTEGER NOT NULL DEFAULT 3600,
    lease_expires_at REAL
);

-- The claim query filters on status+role and orders by priority then age;
-- this index is what keeps that a scan of the queued rows only.
CREATE INDEX IF NOT EXISTS jobs_claim_idx
    ON jobs (status, role, priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS jobs_lease_idx ON jobs (status, lease_expires_at);

CREATE TABLE IF NOT EXISTS artifacts (
    id         TEXT PRIMARY KEY,
    job_id     TEXT NOT NULL,
    name       TEXT NOT NULL,
    path       TEXT NOT NULL,
    size       INTEGER NOT NULL,
    sha256     TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS artifacts_job_idx ON artifacts (job_id);

CREATE TABLE IF NOT EXISTS scale_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    role       TEXT NOT NULL,
    action     TEXT NOT NULL,
    detail     TEXT NOT NULL,
    driver     TEXT NOT NULL
);
"""


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path):
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._local = threading.local()
        # Serialises writers in-process; SQLite's own locking covers the rest.
        self._write_lock = threading.Lock()
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    def connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            conn.row_factory = sqlite3.Row
            # WAL lets the autoscaler read while agents are claiming.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    # -- agents ----------------------------------------------------------

    def enroll_agent(self, name, roles, slots=1, version="", meta=None):
        """Create an agent and return (agent, plaintext_token).

        The plaintext token is returned exactly once and never stored.
        """
        agent = Agent(name, normalise_roles(roles), slots=slots,
                      version=version, meta=meta)
        token = models.new_token()
        agent.token_hash = hash_token(token)
        with self._write_lock:
            self.connection().execute(
                "INSERT INTO agents (id,name,roles,slots,token_hash,enrolled_at,"
                "last_seen,version,meta,draining) VALUES (?,?,?,?,?,?,?,?,?,0)",
                (agent.id, agent.name, json.dumps(agent.roles), agent.slots,
                 agent.token_hash, agent.enrolled_at, agent.last_seen,
                 agent.version, json.dumps(agent.meta)),
            )
        return agent, token

    def get_agent(self, agent_id):
        row = self.connection().execute(
            "SELECT * FROM agents WHERE id=?", (agent_id,)
        ).fetchone()
        return Agent.from_row(row) if row else None

    def authenticate_agent(self, agent_id, token):
        agent = self.get_agent(agent_id)
        if agent is None:
            return None
        import secrets as _secrets
        if _secrets.compare_digest(agent.token_hash, hash_token(token)):
            return agent
        return None

    def list_agents(self):
        rows = self.connection().execute(
            "SELECT * FROM agents ORDER BY name"
        ).fetchall()
        return [Agent.from_row(r) for r in rows]

    def heartbeat(self, agent_id, version=None, meta=None):
        with self._write_lock:
            if meta is not None:
                self.connection().execute(
                    "UPDATE agents SET last_seen=?, version=COALESCE(?,version),"
                    " meta=? WHERE id=?",
                    (models.now(), version, json.dumps(meta), agent_id),
                )
            else:
                self.connection().execute(
                    "UPDATE agents SET last_seen=?, version=COALESCE(?,version)"
                    " WHERE id=?",
                    (models.now(), version, agent_id),
                )

    def set_draining(self, agent_id, draining):
        with self._write_lock:
            self.connection().execute(
                "UPDATE agents SET draining=? WHERE id=?",
                (1 if draining else 0, agent_id),
            )

    def remove_agent(self, agent_id):
        with self._write_lock:
            self.connection().execute("DELETE FROM agents WHERE id=?", (agent_id,))

    # -- jobs ------------------------------------------------------------

    def enqueue(self, job):
        with self._write_lock:
            self.connection().execute(
                "INSERT INTO jobs (id,role,kind,payload,status,priority,created_at,"
                "attempts,max_attempts,timeout_seconds) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (job.id, job.role, job.kind, json.dumps(job.payload), job.status,
                 job.priority, job.created_at, job.attempts, job.max_attempts,
                 job.timeout_seconds),
            )
        return job

    def claim(self, agent):
        """Atomically hand one queued job to an agent, or return None.

        Correctness note: the SELECT and the UPDATE run inside a single
        ``BEGIN IMMEDIATE`` transaction, so two agents polling at the same
        instant can never claim the same row -- the second one's SELECT does
        not see the row as queued any more.
        """
        if agent.draining:
            return None
        roles = normalise_roles(agent.roles)
        if not roles:
            return None

        conn = self.connection()
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if "*" in roles:
                    row = conn.execute(
                        "SELECT * FROM jobs WHERE status=? "
                        "ORDER BY priority DESC, created_at ASC LIMIT 1",
                        (models.QUEUED,),
                    ).fetchone()
                else:
                    placeholders = ",".join("?" * len(roles))
                    row = conn.execute(
                        "SELECT * FROM jobs WHERE status=? AND role IN (%s) "
                        "ORDER BY priority DESC, created_at ASC LIMIT 1"
                        % placeholders,
                        (models.QUEUED, *roles),
                    ).fetchone()
                if row is None:
                    conn.execute("COMMIT")
                    return None

                job = Job.from_row(row)
                started = models.now()
                job.status = models.RUNNING
                job.agent_id = agent.id
                job.started_at = started
                job.attempts += 1
                job.lease_expires_at = started + job.timeout_seconds
                conn.execute(
                    "UPDATE jobs SET status=?, agent_id=?, started_at=?, attempts=?,"
                    " lease_expires_at=? WHERE id=?",
                    (job.status, job.agent_id, job.started_at, job.attempts,
                     job.lease_expires_at, job.id),
                )
                conn.execute("COMMIT")
                return job
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def complete(self, job_id, result=None):
        with self._write_lock:
            self.connection().execute(
                "UPDATE jobs SET status=?, finished_at=?, result=?,"
                " lease_expires_at=NULL WHERE id=?",
                (models.DONE, models.now(), json.dumps(result or {}), job_id),
            )

    def fail(self, job_id, error, retry=True):
        """Fail a job, requeuing it when attempts remain.

        Returns the state the job ended up in, so the caller can log honestly
        instead of assuming it was retried.
        """
        conn = self.connection()
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
                if row is None:
                    conn.execute("COMMIT")
                    return None
                job = Job.from_row(row)
                if retry and job.attempts < job.max_attempts:
                    conn.execute(
                        "UPDATE jobs SET status=?, agent_id=NULL, started_at=NULL,"
                        " error=?, lease_expires_at=NULL WHERE id=?",
                        (models.QUEUED, str(error), job_id),
                    )
                    state = models.QUEUED
                else:
                    conn.execute(
                        "UPDATE jobs SET status=?, finished_at=?, error=?,"
                        " lease_expires_at=NULL WHERE id=?",
                        (models.FAILED, models.now(), str(error), job_id),
                    )
                    state = models.FAILED
                conn.execute("COMMIT")
                return state
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def cancel(self, job_id):
        with self._write_lock:
            cur = self.connection().execute(
                "UPDATE jobs SET status=?, finished_at=?, lease_expires_at=NULL"
                " WHERE id=? AND status IN (?,?)",
                (models.CANCELLED, models.now(), job_id,
                 models.QUEUED, models.RUNNING),
            )
            return cur.rowcount > 0

    def reclaim_expired(self):
        """Requeue jobs whose agent died mid-run. Returns the count."""
        conn = self.connection()
        with self._write_lock:
            rows = conn.execute(
                "SELECT id FROM jobs WHERE status=? AND lease_expires_at IS NOT NULL"
                " AND lease_expires_at < ?",
                (models.RUNNING, models.now()),
            ).fetchall()
        reclaimed = 0
        for row in rows:
            state = self.fail(row["id"], "lease expired -- agent stopped reporting")
            if state is not None:
                reclaimed += 1
        return reclaimed

    def get_job(self, job_id):
        row = self.connection().execute(
            "SELECT * FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        return Job.from_row(row) if row else None

    def list_jobs(self, status=None, role=None, limit=50):
        clauses, params = [], []
        if status:
            clauses.append("status=?")
            params.append(status)
        if role:
            clauses.append("role=?")
            params.append(role)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self.connection().execute(
            "SELECT * FROM jobs %s ORDER BY created_at DESC LIMIT ?" % where,
            params,
        ).fetchall()
        return [Job.from_row(r) for r in rows]

    def queue_depth_by_role(self):
        rows = self.connection().execute(
            "SELECT role, COUNT(*) AS n FROM jobs WHERE status=? GROUP BY role",
            (models.QUEUED,),
        ).fetchall()
        return {r["role"]: r["n"] for r in rows}

    def running_by_role(self):
        rows = self.connection().execute(
            "SELECT role, COUNT(*) AS n FROM jobs WHERE status=? GROUP BY role",
            (models.RUNNING,),
        ).fetchall()
        return {r["role"]: r["n"] for r in rows}

    # -- artifacts -------------------------------------------------------

    def add_artifact(self, job_id, name, path, size, sha256=None):
        artifact_id = models.new_id("art")
        with self._write_lock:
            self.connection().execute(
                "INSERT INTO artifacts (id,job_id,name,path,size,sha256,created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (artifact_id, job_id, name, path, size, sha256, models.now()),
            )
        return artifact_id

    def list_artifacts(self, job_id):
        rows = self.connection().execute(
            "SELECT * FROM artifacts WHERE job_id=? ORDER BY created_at",
            (job_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_artifact(self, artifact_id):
        row = self.connection().execute(
            "SELECT * FROM artifacts WHERE id=?", (artifact_id,)
        ).fetchone()
        return dict(row) if row else None

    # -- scaling log -----------------------------------------------------

    def log_scale_event(self, role, action, detail, driver):
        with self._write_lock:
            self.connection().execute(
                "INSERT INTO scale_events (created_at,role,action,detail,driver)"
                " VALUES (?,?,?,?,?)",
                (models.now(), role, action, detail, driver),
            )

    def recent_scale_events(self, limit=25):
        rows = self.connection().execute(
            "SELECT * FROM scale_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
