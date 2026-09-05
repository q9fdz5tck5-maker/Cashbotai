"""Pluggable capacity drivers.

A driver answers one question: "the queue for role X is backed up -- can you
get me another box?"  The fixed-pool driver answers by waking a machine you
already own; a cloud driver would answer by calling a provider API.  The
autoscaler does not care which, so you can start with the pool you have and
add real provisioning later without touching the scheduler.
"""

from .base import CapacityDriver, ScaleDecision
from .manual import ManualPoolDriver
from .solidseo import SolidSEODriver

_REGISTRY = {
    "manual": ManualPoolDriver,
    "pool": ManualPoolDriver,
    "solidseo": SolidSEODriver,
}


def available():
    return sorted(set(_REGISTRY))


def load(name, config=None):
    """Instantiate a driver by name, with a clear error for typos."""
    key = (name or "manual").strip().lower()
    if key not in _REGISTRY:
        raise ValueError(
            "Unknown driver %r. Available: %s" % (name, ", ".join(available()))
        )
    return _REGISTRY[key](config or {})


__all__ = [
    "CapacityDriver", "ScaleDecision", "ManualPoolDriver", "SolidSEODriver",
    "available", "load",
]
