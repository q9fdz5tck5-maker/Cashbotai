"""Shared helpers for handlers."""

import json
import os
import shutil
import subprocess


class HandlerError(RuntimeError):
    """A handler failed for a reason the operator can act on."""


def require_binary(name, install_hint=""):
    """Fail early and clearly when a tool the job needs is not installed."""
    path = shutil.which(name)
    if path is None:
        hint = (" " + install_hint) if install_hint else ""
        raise HandlerError(
            "%r is not installed on this worker, so this job cannot run.%s"
            % (name, hint)
        )
    return path


def run_command(args, cwd=None, timeout=3600, log=None):
    """Run a subprocess, capturing output and raising with it on failure.

    Handlers must never swallow stderr: when a render dies, the ffmpeg message
    is the entire diagnosis.
    """
    if log:
        log("exec: %s" % " ".join(str(a) for a in args))
    try:
        completed = subprocess.run(
            [str(a) for a in args], cwd=cwd, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    except subprocess.TimeoutExpired:
        raise HandlerError("command timed out after %ss: %s"
                           % (timeout, " ".join(str(a) for a in args)))
    output = completed.stdout.decode("utf-8", "replace")
    if completed.returncode != 0:
        tail = "\n".join(output.strip().splitlines()[-25:])
        raise HandlerError(
            "command failed (exit %d): %s\n%s"
            % (completed.returncode, " ".join(str(a) for a in args), tail)
        )
    return output


def safe_join(base, *parts):
    """Join paths and refuse anything that escapes the working directory."""
    target = os.path.abspath(os.path.join(base, *parts))
    base_abs = os.path.abspath(base)
    if target != base_abs and not target.startswith(base_abs + os.sep):
        raise HandlerError("path %r escapes the job working directory" % (parts,))
    return target


def media_duration(path):
    """Length of an audio or video file in seconds, via ffprobe.

    Timing a slideshow against its narration is the one measurement the
    webinar pipeline cannot do without, so a missing ffprobe is named as such
    rather than surfacing as a KeyError three frames deeper.
    """
    if shutil.which("ffprobe") is None:
        raise HandlerError(
            "ffprobe is needed to measure %s. Install ffmpeg (which ships "
            "ffprobe) on this worker." % os.path.basename(path)
        )
    raw = run_command([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", path,
    ], timeout=120)
    try:
        return float(json.loads(raw)["format"]["duration"])
    except (ValueError, KeyError) as exc:
        raise HandlerError("could not read a duration from %s: %s" % (path, exc))
