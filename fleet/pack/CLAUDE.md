# This folder controls somebody's fleet of computers

The person using this may never have opened a terminal. Talk about their
machines in plain words. "Your video computer is busy" beats "the video role
has zero free slots".

## What is here

A hub (one machine with a web address) and any number of workers that dial
*out* to it and ask for work. Nothing ever connects in to a worker, so a
desktop behind a home router is as usable as a rented server.

You reach all of it through the **fleet** MCP server, which is already wired
up in `.mcp.json`. Use those tools rather than shelling out.

| Tool | For |
|---|---|
| `list_computers` | what machines exist and whether they are on |
| `check_connection` | why something is not working |
| `speak_text` | words to spoken audio |
| `make_video` | a whole narrated video from written sections |
| `make_slide` | one slide, to check a look before committing |
| `check_job` / `list_jobs` | following work |
| `save_result` | writing a finished file to disk |
| `add_computer` | the line to paste on a new machine |
| `run_job` | anything the others do not cover |

## How to be useful here

**Start with `list_computers`.** Most confusion is one machine being offline.
If a tool fails, run `check_connection` before theorising — it separates the
three failures that otherwise look identical.

**Videos are slow.** `make_video` returns a job id after a couple of minutes
rather than blocking. Say so, then follow it with `check_job`. Do not resubmit
a job that is still running — that queues a second one.

**Write the video, do not ask for it.** When someone asks for a video about
their business, draft the sections yourself and build it. Show them the result.
A section is one slide plus the words spoken over it:

```json
{"title": "What we do", "bullets": ["Fast", "Local"],
 "narration": "Here is what we do."}
```

or a diagram — up to five boxes, optional stick figure, optional numbered
outputs, and `"arrows": "loop"` for a return path:

```json
{"kind": "diagram", "title": "It feeds itself",
 "boxes": [{"label": "Website", "note": "gets made"},
           {"label": "Video", "note": "about the website"}],
 "arrows": "loop", "loop_label": "what comes out goes back in",
 "narration": "What comes out of one becomes what goes into the next."}
```

Each slide is held for exactly as long as its narration takes to speak, so
write narration at the length you want the slide on screen. Keep it to plain
spoken English — it is going to be read out loud, so no bullet fragments, no
jargon, and spell out anything an AI voice would mangle.

**Roles.** `audio` speaks, `video` renders, `webinar` does whole pipelines,
`general` is anything unpinned. `general` is not a wildcard. Leave the role
alone unless there is a reason.

## Things worth saying out loud to the person

- Their private code is in `MY-FLEET-DETAILS.txt`. Anyone holding it can run
  work on their machines. It is a password.
- Adding a computer is one pasted line. If they are waiting on renders, that
  is the answer.
- Files the fleet produces live on the hub until downloaded. `save_result`
  brings one back to this machine.

## The plain-words docs

`START-HERE.txt` for setup, `USE-WITH-CLAUDE.txt` for this, `GET-COMPUTERS.txt`
for buying machines, `TECHNICAL.md` for how it all works underneath. If someone
asks a setup question, the answer is probably already written in one of those
in words they will understand — point at it rather than paraphrasing.
