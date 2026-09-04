"""Job handlers: the code that actually runs on a worker box.

A handler is a callable ``run(payload, ctx) -> dict``. It receives the job's
payload, does the work inside ``ctx.workdir``, registers any output files with
``ctx.artifact(path)``, and returns a JSON-serialisable summary. Raising is how
a handler reports failure -- the agent turns the exception into a job failure
with the message attached.
"""

from .render import run as render_run
from .shell import run as shell_run
from .slides import run as deck_run
from .tts import run as tts_run
from .webinar import run as webinar_run

# kind -> handler. The agent looks jobs up here by their `kind` field.
REGISTRY = {
    "tts": tts_run,
    "render": render_run,
    "deck": deck_run,
    "webinar": webinar_run,
    "shell": shell_run,
}


def get(kind):
    """Resolve a handler, listing what *is* available when one is missing."""
    handler = REGISTRY.get(kind)
    if handler is None:
        raise KeyError(
            "No handler for job kind %r. This agent knows: %s"
            % (kind, ", ".join(sorted(REGISTRY)))
        )
    return handler


def register(kind, handler):
    """Add your own handler -- this is the extension point for new apps."""
    REGISTRY[kind] = handler
