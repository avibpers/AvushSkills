# Summary templates

A template decides what a summary contains and how it looks. It is one Markdown
file: a YAML header for the layout, and a body that is the **system prompt** an
AI model follows to write `brief.json` from a transcript. The same file works in
this skill and in the Koli app (which loads templates as its AI system prompt).

## Where templates live

| Folder | What | Who writes it |
|---|---|---|
| `<skill>/templates/` | Built-in: `standard`, `board-meeting`, and `_common.md` (shared rules) | ships with the skill |
| `~/.claude/meeting-templates/` | The user's own collection | this skill (create, edit, delete) |
| `%APPDATA%\koli\summary_templates\` (`~/.koli/summary_templates`) | Koli's collection, when Koli is installed | the Koli app |

A template in a later folder with the same `id` replaces an earlier one, so a
user can override a built-in by saving a copy with the same id. New and edited
templates always go to `~/.claude/meeting-templates/`; never edit the built-ins.

`python scripts/templates.py list | show <id> | prompt <id> | check <file> | dirs`

## The header

```yaml
---
id: weekly-sync                 # lowercase, digits, hyphens; also the file name
name: Weekly team sync          # shown in the list
description: One line on what this summary is for and what it contains.
language: meeting               # "meeting" = the language most of the meeting was in; or an ISO code such as he, en
title:
  mode: generated               # generated = the AI names the meeting; fixed = one of the choices
  choices: ["Weekly Sync"]      # needed for mode fixed
date: date                      # date (no time) or datetime
blocks: [header, tldr, decisions, action_items, sections, next_meeting, data]
doc_blocks: [header, tldr, decisions, action_items, sections, next_meeting]   # optional, Google Doc order
labels:                         # optional heading overrides
  next_meeting: Carried over
---
```

**Blocks** (the full list is `BLOCKS` in `scripts/templates.py`; `check` rejects others):

| Block | Shows | Fed by |
|---|---|---|
| `header` | title, date (+ duration and speakers when `date: datetime`) | `title`, `date` |
| `tldr` | short summary paragraphs | `tldr` |
| `quick` | Google Doc only: compact bottom lines | `tldr`, decisions, actions, open, parked |
| `counts` | web only: number cards | — |
| `participants` | attendees with roles | `attendees`, else the speakers |
| `agenda` | numbered agenda | `agenda[].title` |
| `agenda_details` | per item: discussion, decisions, action items | `agenda[]` |
| `decisions` | all decisions | `decisions`, else all `agenda[].decisions` |
| `action_items` | all actions as a table | `action_items`, else all `agenda[].action_items` |
| `lists` / `open_questions` / `parked` | open and parked items | `open_questions`, `parked` |
| `next_meeting` | points for the next meeting | `next_meeting` |
| `speakers` | talk-time charts and roles | the transcript, `roles` |
| `topics` | topic cards with points and quotes | `topics` |
| `sections` | anything else, as titled bullets or paragraphs | `sections: [{title, items[], text[]}]` |
| `notes` | transcript quality notes | `notes` |
| `transcript` | the full transcript | the transcript |
| `data` | web only: the brief as JSON | the brief |
| `page_break` | Google Doc only: new page | — |

**Labels**: keys are block names plus `agenda_discussion`, `agenda_decisions`,
`agenda_actions`, `task`, `owner`, `status`, `due`. Order of precedence:
`labels` in brief.json (the AI may translate headings), then the template's
`labels`, then English defaults. A template that wants fixed headings says so
in its body ("Keep the section headings as given").

## The body (the system prompt)

Write it to an AI model that has only the transcript in front of it:

1. One paragraph: what this summary is for and who reads it.
2. The structure, section by section, in plain instructions.
3. `{{common_rules}}` on its own line (shared rules from `_common.md`).
4. `## What to return` with a ```json example of the full brief, using only the
   fields its blocks need (see `references/brief-format.md`), with `"template": "<id>"`.
5. Short notes on fields that need them.

The language rule is added automatically from the header's `language`.

## Creating a template

Ask what the summary is for if it isn't clear, then pick one way:

- **From a description.** The user lists the sections they want (like a board
  minutes spec). Map each section to a block; anything with no block becomes a
  `sections` entry the prompt asks for by its exact title.
- **From example summaries.** The user attaches past summaries (files, pasted
  text, Google Docs). Read them all and note what they share: fixed title or
  not, date style, heading names and order, bullets or prose, length per
  section, tone, how owners and dates of tasks are written, what is never
  included. Build the template from the shared pattern; quote their heading
  names in `labels`. When examples disagree, follow the majority and tell the user.
- **From an existing template.** Copy it under a new id and change what the user asks.

Then:

1. Write `~/.claude/meeting-templates/<id>.md`.
2. `python scripts/templates.py check <file>`; fix every problem it lists.
3. Show the user the template's sections in a few lines and offer a preview on
   their latest transcript (or a short sample), rendered as an HTML file or artifact.

Editing: change the user's copy (copy a built-in first). Deleting: only the
user's own templates, and only after they confirm.
