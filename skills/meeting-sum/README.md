# meeting-sum

Turn a meeting transcript into a clear, shareable summary.

- **Reads almost any transcript.** Google Meet caption exports (it cleans up their repeated,
  growing lines), Zoom and Teams `.vtt` / `.srt`, Koli meeting files, other JSON transcripts,
  and plain `Name: text` notes. With no timestamps, it estimates times from word counts.
- **Writes from a template.** Two come built in, and you can make your own:
  - **Visual meeting brief** (`standard`): summary, decisions, action items with owners,
    open questions, who talked most with charts, topic cards with quotes, the full
    transcript, and the summary as JSON for other AI tools.
  - **Board / management meeting** (`board-meeting`): formal minutes with a fixed title,
    the date, participants, the agenda, then for each agenda item the discussion,
    decisions and action items, and points for the next meeting.
- **Delivers where you want it.** A Claude artifact (a private web page link), a local HTML
  file, and/or a Google Doc in the Drive folder you choose. It checks the Google Drive
  connection first and tells you if it's missing.
- **Writes in the meeting's language by default.** It asks only when you haven't said and
  the template doesn't set a language.

## Use it

Attach or point to a transcript and ask for a summary, or run the command:

```text
/meeting-sum                                   (Claude Code quick install)
/avush-skills:meeting-sum                      (Claude Code plugin)
/meeting-sum gdoc board-meeting ~/Downloads/meeting_captions.txt
```

It asks which template, which outputs, and (if needed) which language, then gives you the links
and file paths at the end.

## Templates

```text
/meeting-sum templates
```

lists your templates and offers to create one:

- **from a description**: say which sections you want, in which order, with which headings;
- **from past summaries**: attach a few summaries you already like, and it works out their
  shared structure and headings and turns that into a template;
- **from an existing template**: copy it and change what you need.

A template is one Markdown file. Its header sets the look (title, date style, language, the
sections and their order, the headings). Its body is the instruction the AI follows to write
the summary, so the same file can serve as the system prompt in other apps.

| Where | What |
|---|---|
| `templates/` in this skill | Built-in templates and the shared rules (`_common.md`) |
| `~/.claude/meeting-templates/` | Your own templates. Updates never touch them. |
| `%APPDATA%\koli\summary_templates\` | Templates from the Koli app, when installed |

Details: [references/templates.md](references/templates.md).

## Needs

- Python 3.9 or newer where the AI runs the scripts (already there on claude.ai and ChatGPT).
- For Google Docs: a Google Drive connector in your AI app.
- Artifacts work in Claude only; elsewhere, use the HTML file.

## Files

| File | Job |
|---|---|
| `SKILL.md` | The steps the AI follows |
| `scripts/normalize.py` | Cleans any transcript into one JSON shape |
| `scripts/templates.py` | Lists, checks and builds prompts from templates |
| `scripts/render.py` | Lays out the web page and the Google Doc from a template |
| `references/brief-format.md` | Every field a summary can have |
| `references/templates.md` | How templates work and how to make one |
