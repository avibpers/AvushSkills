# brief.json: every field

`brief.json` is what an AI writes from a transcript, following a template's
system prompt (`python scripts/templates.py prompt <id>`). This file lists every
field any template may use, so new templates stay compatible with the renderer
and with the Koli app (it is the Koli "brief v1" format, extended).

All times are **seconds from the start of the transcript** (the `start` of the
turn where the thing was said). Ids: D1… for decisions, A1… for actions, Q1…
open questions, P1… parked, N1… next meeting, T1… topics, "1", "2"… agenda.

| Field | Shape | Notes |
|---|---|---|
| `version` | `1` | |
| `template` | template id | which layout renders it |
| `generator` | text | who wrote it, e.g. "meeting-sum skill" |
| `title` | text | for fixed-title templates, one of the template's choices |
| `date` | ISO date or date-time | |
| `language` | ISO code | the language the report is written in; he/ar make it right to left |
| `participants` | `{speaker id: display name}` | renames transcript speakers |
| `attendees` | `[{name, role?}]` | the people listed in formal minutes |
| `tldr` | `[paragraph]` | |
| `decisions` | `[{id, text, at}]` | |
| `action_items` | `[{id, task, owner, status, due, at, effort?}]` | status: do_now, plan_only, waiting, done; owner and due null unless said |
| `open_questions` | `[{id, text, at}]` | |
| `parked` | `[{id, text, at}]` | |
| `next_meeting` | `[{id, text, at}]` | unresolved points to carry over |
| `agenda` | `[{id, title, start?, discussion: [text], decisions: [...], action_items: [...]}]` | decisions/actions shaped as above |
| `topics` | `[{id, title, start, end, led_by, lead, points: [text], quotes: [{text, who, at}]}]` | |
| `roles` | `{speaker id: one line}` | |
| `sections` | `[{id, title, items?: [text], text?: [paragraph]}]` | custom sections a template asks for by title |
| `labels` | `{block: heading}` | translated headings, when the template allows |
| `notes` | `[text]` | transcript quality problems |

When decisions and actions live inside `agenda`, leave the top-level lists out;
the renderer and other tools collect them from the agenda items.
