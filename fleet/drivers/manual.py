"""Fixed pool of machines you already own.

This driver does not create anything. It reads your server inventory, works out
which listed boxes are not currently enrolled and reporting, and tells you
exactly which one to bring online. That is the truthful answer for a pool of
pre-paid VPS boxes: capacity is a machine you already pay for that is sitting
idle, and "scaling up" means starting its agent.
"""

import json
import os

from .base import CapacityDriver, ScaleDecision


class ManualPoolDriver(CapacityDriver):
    name = "manual"

    def __init__(self, config=None):
        super().__init__(config)
        self.inventory_path = self.config.get("inventory", "fleet.servers.json")

    def load_inventory(self):
        """Read the server list. Missing file is not an error -- just no pool."""
        if not os.path.exists(self.inventory_path):
            return []
        with open(self.inventory_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("servers", data if isinstance(data, list) else [])

    def _idle_candidates(self, role, context):
        online_names = {
            agent["name"] for agent in context.get("agents", [])
            if agent.get("state") == "online"
        }
        candidates = []
        for server in self.load_inventory():
            roles = [str(r).lower() for r in server.get("roles", [])]
            if role in roles or "*" in roles:
                if server.get("name") not in online_names:
                    candidates.append(server)
        return candidates

    def scale_up(self, role, deficit, context):
        candidates = self._idle_candidates(role, context)
        if not candidates:
            return ScaleDecision(
                "scale_up", role,
                "Queue for role '%s' needs %d more slot(s), but every box in "
                "your inventory tagged '%s' is already online. Add another "
                "server to %s, or accept the queue wait."
                % (role, deficit, role, self.inventory_path),
                fulfilled=False,
            )
        names = [c.get("name", "?") for c in candidates[:deficit]]
        return ScaleDecision(
            "scale_up", role,
            "Queue for role '%s' needs %d more slot(s). These inventory boxes "
            "are tagged '%s' but not reporting: %s. Start their agent to absorb "
            "the queue." % (role, deficit, role, ", ".join(names)),
            fulfilled=False,
            instance={"candidates": names},
        )

    def scale_down(self, role, surplus, context):
        return ScaleDecision(
            "scale_down", role,
            "Role '%s' has %d idle slot(s). Fixed-pool boxes are already paid "
            "for, so nothing is shut down automatically." % (role, surplus),
            fulfilled=False,
        )
