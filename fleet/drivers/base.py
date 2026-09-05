"""The driver contract."""


class ScaleDecision:
    """What a driver did, or wants a human to do.

    ``fulfilled`` is the honest bit: a fixed-pool driver cannot conjure a
    machine, so it returns fulfilled=False with an instruction. The autoscaler
    surfaces that instead of pretending capacity arrived.
    """

    def __init__(self, action, role, detail, fulfilled=False, instance=None):
        self.action = action          # "scale_up" | "scale_down" | "noop"
        self.role = role
        self.detail = detail
        self.fulfilled = fulfilled
        self.instance = instance

    def to_dict(self):
        return {
            "action": self.action,
            "role": self.role,
            "detail": self.detail,
            "fulfilled": self.fulfilled,
            "instance": self.instance,
        }

    def __repr__(self):
        return "<ScaleDecision %s %s fulfilled=%s>" % (
            self.action, self.role, self.fulfilled,
        )


class CapacityDriver:
    """Subclass this to teach the fleet how to get more machines."""

    name = "base"

    def __init__(self, config=None):
        self.config = config or {}

    def scale_up(self, role, deficit, context):
        """Called when role needs `deficit` more concurrent slots."""
        raise NotImplementedError

    def scale_down(self, role, surplus, context):
        """Called when role has `surplus` idle slots. Optional."""
        return ScaleDecision("noop", role, "driver does not scale down")

    def describe(self):
        return {"driver": self.name, "config": self.redacted_config()}

    def redacted_config(self):
        """Never let an API key reach a log line or an HTTP response."""
        secret_ish = ("token", "key", "secret", "password", "api")
        out = {}
        for key, value in self.config.items():
            if any(s in key.lower() for s in secret_ish):
                out[key] = "***redacted***"
            else:
                out[key] = value
        return out
