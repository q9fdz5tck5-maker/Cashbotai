---
name: fleet
description: Drive a fleet of worker computers — list machines and whether they are online, generate AI speech, build narrated videos from written sections, draw slides, follow jobs, download finished files, and add new machines. Use whenever someone asks about "my computers", "my servers", "my fleet", asks for a video or voiceover to be made, asks why work is not running, or asks how to add another machine.
---

# Driving the fleet

Work through the **fleet** MCP tools. They are already connected — do not shell
out to `fleet.py` or `curl` unless a tool genuinely cannot do the job.

## Start here

`list_computers` first, almost always. It answers "is anything on?", "why is
nothing happening?", and "what can I ask for?" in one call.

If any tool fails, `check_connection` before guessing. It distinguishes the
three failures that look identical from the outside: the port is blocked, the
secure connection does not verify, or the access code is wrong.

## Making a video

`make_video` takes a list of sections. Each section is one slide plus the words
spoken over it, and the slide is held for exactly as long as the narration
takes — so narration length *is* slide length.

Two shapes of section:

**Text slide** — `title`, optional `subtitle`, optional `bullets`.

**Diagram** — `"kind": "diagram"` plus:

- `boxes` — up to five, each `{label, note}`
- `person: true` — a stick figure at the left, with an arrow into the row
- `outputs` — a numbered list drawn underneath
- `arrows` — `"right"` between boxes, or `"loop"` to add the return path
- `loop_label`, `caption`

Write narration as spoken English. It is read aloud: no bullet fragments, no
jargon, no "e.g.", and expand anything a voice would mangle — write "A I", not
"AI", when it should be said as letters.

Draft the sections yourself rather than asking the person to write them. Offer
`make_slide` on one section first if the look matters.

Videos take minutes. `make_video` hands back a job id; follow it with
`check_job`, and do not resubmit — that queues a second video.

## Getting the file

`check_job` lists the finished files with ids. `save_result` writes one to
disk. Say where you put it.

## Adding a machine

`add_computer` returns the exact line to paste. If the fleet is slow, this is
the answer — more machines, not different settings.

## Tone

Plain words. The person may never have opened a terminal. Do not name roles,
slots, or job kinds unless they ask; say "your video computer" and "still
going".
