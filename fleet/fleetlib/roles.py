"""Roles describe what a machine is *for*.

A box tagged ``audio`` runs voice generation, a box tagged ``video`` runs
renders, a box tagged ``webinar`` hosts the builder app itself.  A job asks for
one role; the scheduler only ever hands it to an agent that declares it.
"""

# Canonical roles. Anything else is allowed too (roles are free-form strings),
# these are just the ones the built-in handlers and the CLI know how to talk
# about.
AUDIO = "audio"
VIDEO = "video"
WEBINAR = "webinar"
GENERAL = "general"

KNOWN_ROLES = {
    AUDIO: "AI voice / TTS generation",
    VIDEO: "Video rendering and encoding",
    WEBINAR: "Webinar builder app and composite pipelines",
    GENERAL: "Anything not pinned to a specialised box",
}


def normalise_roles(roles):
    """Lowercase, strip, de-duplicate, and keep a stable order."""
    seen = []
    for role in roles or ():
        cleaned = str(role).strip().lower()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def agent_can_run(agent_roles, job_role):
    """True when an agent is allowed to pick up a job.

    An agent matches when it declares the job's role outright, or when it
    declares the wildcard ``*``. ``general`` is deliberately not a wildcard --
    it is an ordinary role, so that a box you tagged ``general`` never quietly
    starts stealing GPU renders.
    """
    roles = set(normalise_roles(agent_roles))
    return "*" in roles or str(job_role).strip().lower() in roles


def describe(role):
    return KNOWN_ROLES.get(role, "custom role")
