"""Decide when a role needs more machines.

The rule is deliberately boring: compare outstanding work against the slots
that are actually reporting, and only act once the gap has persisted. Reacting
to a single poll makes a fleet flap -- one burst of ten short TTS jobs would
demand ten boxes it does not need three seconds later.
"""

import time

from .models import ONLINE
from .roles import normalise_roles


class Autoscaler:
    """Computes per-role capacity gaps and asks a driver to close them.

    Parameters
    ----------
    sustain_seconds
        A deficit must hold for this long before scale-up fires.
    cooldown_seconds
        Minimum gap between two scale actions for the same role.
    scale_down_after
        Idle capacity must persist this long before scale-down is suggested.
    """

    def __init__(self, store, driver, sustain_seconds=60, cooldown_seconds=300,
                 scale_down_after=900, enabled=True):
        self.store = store
        self.driver = driver
        self.sustain_seconds = sustain_seconds
        self.cooldown_seconds = cooldown_seconds
        self.scale_down_after = scale_down_after
        self.enabled = enabled
        # role -> timestamp the current deficit/surplus was first observed
        self._deficit_since = {}
        self._surplus_since = {}
        self._last_action = {}

    # -- measurement -----------------------------------------------------

    def capacity_by_role(self, agents):
        """Concurrent slots that are genuinely available right now.

        Draining and non-online agents contribute nothing, because a slot on a
        box that stopped heartbeating is not capacity -- it is a lie that would
        suppress a scale-up exactly when one is needed.
        """
        capacity = {}
        for agent in agents:
            if agent.draining or agent.state() != ONLINE:
                continue
            for role in normalise_roles(agent.roles):
                capacity[role] = capacity.get(role, 0) + agent.slots
        return capacity

    def snapshot(self):
        """A full picture of demand vs capacity, per role."""
        agents = self.store.list_agents()
        capacity = self.capacity_by_role(agents)
        queued = self.store.queue_depth_by_role()
        running = self.store.running_by_role()

        roles = set(capacity) | set(queued) | set(running)
        report = {}
        for role in sorted(roles):
            demand = queued.get(role, 0) + running.get(role, 0)
            slots = capacity.get(role, 0)
            report[role] = {
                "queued": queued.get(role, 0),
                "running": running.get(role, 0),
                "demand": demand,
                "capacity": slots,
                "deficit": max(0, demand - slots),
                "surplus": max(0, slots - demand),
            }
        return {"roles": report, "agents": [a.to_dict() for a in agents]}

    # -- decision --------------------------------------------------------

    def _cooling_down(self, role, now):
        last = self._last_action.get(role)
        return last is not None and (now - last) < self.cooldown_seconds

    def evaluate(self, now=None):
        """Return the list of ScaleDecisions taken this tick."""
        if not self.enabled:
            return []
        now = now if now is not None else time.time()
        state = self.snapshot()
        context = {"agents": state["agents"], "roles": state["roles"]}
        decisions = []

        for role, stats in state["roles"].items():
            deficit = stats["deficit"]
            surplus = stats["surplus"]

            if deficit > 0:
                self._surplus_since.pop(role, None)
                first_seen = self._deficit_since.setdefault(role, now)
                if now - first_seen < self.sustain_seconds:
                    continue
                if self._cooling_down(role, now):
                    continue
                decision = self.driver.scale_up(role, deficit, context)
                self._last_action[role] = now
                self._deficit_since.pop(role, None)
                decisions.append(decision)
                self.store.log_scale_event(
                    role, decision.action, decision.detail, self.driver.name
                )
                continue

            self._deficit_since.pop(role, None)

            # Only consider shrinking when there is genuinely nothing to do.
            if surplus > 0 and stats["demand"] == 0:
                first_seen = self._surplus_since.setdefault(role, now)
                if now - first_seen < self.scale_down_after:
                    continue
                if self._cooling_down(role, now):
                    continue
                decision = self.driver.scale_down(role, surplus, context)
                self._last_action[role] = now
                self._surplus_since.pop(role, None)
                if decision.action != "noop":
                    decisions.append(decision)
                    self.store.log_scale_event(
                        role, decision.action, decision.detail, self.driver.name
                    )
            else:
                self._surplus_since.pop(role, None)

        return decisions
