"""Provider-API driver, shaped for SolidSEOVPS but usable for any host.

Honest status: SolidSEOVPS does not publish a documented instance-creation API
of the sort this driver would need, so the provider path is *not* implemented
against a real endpoint -- it would be guesswork, and guessed API calls that
silently do nothing are worse than none.

What does work today is ``webhook`` mode: you point this driver at any HTTPS
endpoint you control (a provisioning script behind a small handler, a Zapier or
n8n hook, another host's API) and it POSTs a scale request there. That gives
you genuine automatic scaling without waiting on a provider API, and the moment
SolidSEO exposes one, only ``_provider_scale_up`` below needs filling in.
"""

import json

from ..fleetlib.client import FleetClient, FleetError
from .base import CapacityDriver, ScaleDecision


class SolidSEODriver(CapacityDriver):
    name = "solidseo"

    def __init__(self, config=None):
        super().__init__(config)
        # "webhook" is implemented; "provider" intentionally raises.
        self.mode = self.config.get("mode", "webhook")
        self.webhook_url = self.config.get("webhook_url")
        self.webhook_token = self.config.get("webhook_token")
        self.max_instances = int(self.config.get("max_instances", 10))

    def scale_up(self, role, deficit, context):
        if self.mode == "webhook":
            return self._webhook_scale_up(role, deficit, context)
        return self._provider_scale_up(role, deficit, context)

    def _webhook_scale_up(self, role, deficit, context):
        if not self.webhook_url:
            return ScaleDecision(
                "scale_up", role,
                "solidseo driver is in webhook mode but no webhook_url is "
                "configured, so no capacity request was sent.",
                fulfilled=False,
            )
        online = len([
            a for a in context.get("agents", []) if a.get("state") == "online"
        ])
        if online >= self.max_instances:
            return ScaleDecision(
                "scale_up", role,
                "Refusing to scale past max_instances=%d (currently %d online). "
                "Raise the cap deliberately if you want more spend."
                % (self.max_instances, online),
                fulfilled=False,
            )
        try:
            client = FleetClient(self.webhook_url, token=self.webhook_token)
            response = client.post("", body={
                "action": "scale_up",
                "role": role,
                "deficit": deficit,
                "online_agents": online,
            })
            return ScaleDecision(
                "scale_up", role,
                "Requested %d more '%s' box(es) via webhook: %s"
                % (deficit, role, json.dumps(response)[:300]),
                fulfilled=True,
                instance=response if isinstance(response, dict) else None,
            )
        except FleetError as exc:
            # A failed webhook must not look like success -- the queue is still
            # backed up and the operator needs to know why.
            return ScaleDecision(
                "scale_up", role,
                "Scale-up webhook failed (%s). Queue for '%s' is still short "
                "%d slot(s)." % (exc, role, deficit),
                fulfilled=False,
            )

    def _provider_scale_up(self, role, deficit, context):
        raise NotImplementedError(
            "SolidSEOVPS provider mode is not implemented: there is no "
            "documented instance-creation API to call, and inventing one would "
            "fail silently at the worst moment. Use mode='webhook' and point "
            "webhook_url at a provisioning endpoint you control, or implement "
            "this method against your provider's real API."
        )
