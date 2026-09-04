"""Job and agent records shared by the hub, the agents, and the CLI."""

import json
import secrets
import time
import uuid

# Job lifecycle. A job only ever moves forward through these.
QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

TERMINAL_STATES = {DONE, FAILED, CANCELLED}

# Agent lifecycle, derived from heartbeat recency rather than stored directly.
ONLINE = "online"
STALE = "stale"
OFFLINE = "offline"


def new_id(prefix):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:16])


def new_token():
    return secrets.token_urlsafe(32)


def now():
    return time.time()


class Job:
    """One unit of work pinned to a role."""

    __slots__ = (
        "id", "role", "kind", "payload", "status", "priority", "created_at",
        "started_at", "finished_at", "agent_id", "attempts", "max_attempts",
        "error", "result", "timeout_seconds", "lease_expires_at",
    )

    def __init__(self, role, kind, payload=None, priority=0, max_attempts=3,
                 timeout_seconds=3600, job_id=None):
        self.id = job_id or new_id("job")
        self.role = role
        self.kind = kind
        self.payload = payload or {}
        self.status = QUEUED
        self.priority = priority
        self.created_at = now()
        self.started_at = None
        self.finished_at = None
        self.agent_id = None
        self.attempts = 0
        self.max_attempts = max_attempts
        self.error = None
        self.result = None
        self.timeout_seconds = timeout_seconds
        self.lease_expires_at = None

    def to_dict(self):
        return {slot: getattr(self, slot) for slot in self.__slots__}

    @classmethod
    def from_row(cls, row):
        job = cls.__new__(cls)
        for slot in cls.__slots__:
            value = row[slot]
            if slot in ("payload", "result") and isinstance(value, str):
                value = json.loads(value) if value else None
            setattr(job, slot, value)
        return job

    @property
    def duration(self):
        if self.started_at is None:
            return None
        return (self.finished_at or now()) - self.started_at


class Agent:
    """One enrolled machine."""

    __slots__ = (
        "id", "name", "roles", "slots", "token_hash", "enrolled_at",
        "last_seen", "version", "meta", "draining",
    )

    def __init__(self, name, roles, slots=1, agent_id=None, version="",
                 meta=None):
        self.id = agent_id or new_id("agt")
        self.name = name
        self.roles = list(roles)
        self.slots = max(1, int(slots))
        self.token_hash = None
        self.enrolled_at = now()
        self.last_seen = now()
        self.version = version
        self.meta = meta or {}
        self.draining = False

    def state(self, online_window=90, stale_window=600):
        """Online/stale/offline from heartbeat age, not from a stored flag.

        A stored flag would lie the moment a box loses power; heartbeat age
        cannot.
        """
        age = now() - (self.last_seen or 0)
        if age <= online_window:
            return ONLINE
        if age <= stale_window:
            return STALE
        return OFFLINE

    def to_dict(self, redact=True):
        data = {slot: getattr(self, slot) for slot in self.__slots__}
        if redact:
            data.pop("token_hash", None)
        data["state"] = self.state()
        data["last_seen_ago"] = round(now() - (self.last_seen or 0), 1)
        return data

    @classmethod
    def from_row(cls, row):
        agent = cls.__new__(cls)
        for slot in cls.__slots__:
            value = row[slot]
            if slot in ("roles", "meta") and isinstance(value, str):
                value = json.loads(value) if value else ([] if slot == "roles" else {})
            if slot == "draining":
                value = bool(value)
            setattr(agent, slot, value)
        return agent
