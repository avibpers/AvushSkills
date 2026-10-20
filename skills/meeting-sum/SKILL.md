---
name: meeting-sum
description: Turns a meeting transcript into a shareable summary from a template (a visual brief with charts, formal board/management minutes, or the user's own) as a Claude artifact, a local HTML file and/or a Google Doc, and manages the template collection (list, create from a description or from past summaries, edit, delete). Use when the user attaches or points to a meeting transcript (Google Meet captions .txt, Koli meeting .json, Zoom/Teams .vtt/.srt, plain speaker-by-line notes) and wants it summarized, wants to make or change a summary template, or runs /meeting-sum. Arguments may name the output (artifact, html, gdoc), a template id, a language, the word "templates", and a file.
---

# Meeting summary

Two jobs:

- **Summarize a meeting** with a template, in the formats the user picks: a **Claude
  artifact** (a private web page link), a **local HTML file**, or a **Google Doc**.
- **Manage templates**: list them, create one (from a description, from past summaries
  the user attaches, or from an existing template), edit, delete.

Use the template flow when `$ARGUMENTS` says `templates`, the user asks about templates,
or the user attaches past *summaries* (not a transcript) to build a template from. Then
read `references/templates.md` and follow it. Otherwise summarize.

Every summary comes from two files, so all formats agree:

- `transcript.json`: the cleaned transcript, made by `scripts/normalize.py`
- `brief.json`: the summary you write by following the template's system prompt

Paths below are relative to this skill's folder. Run the scripts with `python` (or `python3`
where `python` isn't found); they need Python 3.9+ and nothing else. Speak to the user in
their language. Keep updates short.

This skill works in Claude Code, Cursor, Grok Build and other agents that read skills. Where
it says to ask the user, use your question tool if you have one (AskUserQuestion in Claude
Code); otherwise ask a short numbered question in the chat and wait for the answer.

## 1. Get the transcript

- `$ARGUMENTS` may hold a path, format words (`artifact`, `html`, `gdoc` / `google doc`,
  `all`), a template id, and a language.
- A file the user attached or named: use it.
- Text pasted into the chat only: save it with the Write tool to a `.txt` file in the
  scratchpad (or temp) folder first; the charts and the transcript section need the file.
- Nothing given: ask for the transcript and stop until it arrives.

## 2. Clean it

```bash
python scripts/normalize.py "<transcript file>" -o "<work dir>/transcript.json"
```

The work dir is the scratchpad folder if there is one, else a temp folder. It prints
turns, speakers, words and whether times are `real` or `estimated`. Google Meet caption
exports repeat every caption as it grows; the script keeps the final version of each and
drops page junk, so read `transcript.json`, not the raw file. Read it fully, and note the
language most of the meeting was spoken in.

If it finds no turns, read the raw file yourself and write `transcript.json` by hand in the
same shape (`speakers: [{id, name}]`, `turns: [{speaker, start, end, text}]`, `timing`,
`words`, `duration_s`).

## 3. Template, formats, language

```bash
python scripts/templates.py list
```

See what this session can do: **Artifact** needs Claude's `Artifact` tool (Claude Code or claude.ai); **Google Doc** needs
a Google Drive tool that creates files (such as `create_file` and `search_files` from the
Google Drive connector); **HTML file** always works.

Ask what `$ARGUMENTS` and the conversation haven't settled, in **one** round of questions:

1. "Which template?" Up to three templates, the most fitting first (`standard` unless the
   meeting is clearly a board or management meeting), plus "Create a new template". "Other"
   lets the user name any template in the list. If they pick "Create a new template", run the
   template flow, then come back here with the new template.
2. "How do you want the summary?" (multiSelect): Claude artifact · HTML file · Google Doc.
   List unavailable ones too, with "not connected in this session" in the description.

**Language.** The report is written in the meeting's language by default. Settle it in
this order, and ask only when nothing above the question decides it:

1. The user already said which language (in the arguments or earlier in the conversation).
2. The chosen template sets `language` to a code other than `meeting` (see `templates.py show <id>`).
3. Otherwise ask "Which language should the report be in?" with the meeting's language
   first and marked recommended, then the user's own language if different.

## 4. Check the Google connection (only if Google Doc was picked)

1. Call the Drive search tool once with a tiny query (`pageSize` 1). If the tool is missing
   or the call fails, tell the user Google Drive isn't connected and that they can connect it
   in their Claude connector settings (claude.ai > Settings > Connectors > Google Drive). Go
   on with the other formats they picked; if Google Doc was the only one, make the HTML file
   instead and say so.
2. If it works, ask where to keep the doc: "My Drive (root)" first and recommended, or a
   folder name typed under "Other". No answer means the root.
3. For a folder name, search
   `title = '<name>' and mimeType = 'application/vnd.google-apps.folder'`. Use the first
   hit's id; if there is none, create the folder (`mimeType`
   `application/vnd.google-apps.folder`) and use its id. The root needs no parent id.

## 5. Write brief.json

```bash
python scripts/templates.py prompt <template id>
```

That output is your instruction for this step: follow it exactly to write
`<work dir>/brief.json` from the transcript. If the language was settled in step 3 and
differs from what the prompt's Language section says, the settled language wins.
`references/brief-format.md` lists every field, if you need it.

## 6. Render

```bash
python scripts/render.py "<work dir>/brief.json" "<work dir>/transcript.json" --template <id> \
  --html "<html path>" --gdoc "<work dir>/gdoc.html"
```

Give only the flags you need (`--html` serves both the artifact and the HTML file).

- **HTML file path**: next to the transcript file, named `<YYYY-MM-DD> <title>.html`, with
  characters `\ / : * ? " < > |` replaced. If that folder isn't writable, use the current folder.
- **Artifact only**: write the page into the work dir.

## 7. Deliver

- **Artifact**: publish the `--html` file with the Artifact tool, with `icon: "meeting"` and a
  one-sentence `description`. The page already meets the artifact page contract (title,
  colour tokens with light and dark themes, phone width, fonts from Google Fonts only), so
  publish it as is.
- **HTML file**: nothing more; it's already saved.
- **Google Doc**: read `gdoc.html` and call the Drive create-file tool with `title` = the
  report title (add the date when the title is a fixed one such as "Board Meeting Summary"),
  `textContent` = the file's contents, `contentMimeType` = `text/html`, and `parentId` when a
  folder was chosen. If `gdoc.html` is over about 150 KB, render again with `--no-transcript`
  and say the transcript was left out of the doc because of its size. Take the link from the
  result (`webViewLink`, or `https://docs.google.com/document/d/<id>/edit`).

## 8. Finish

End with a few short lines: one line on the meeting (title and main outcome), each result
(the artifact link, the HTML file's full path, the Google Doc link), the template and
language used, and anything that didn't happen and why.

## Without a shell

If you can't run Python (for example in a claude.ai chat without code tools), do the same
steps by hand: read the template file in `templates/` and follow its body as your
instructions (with `_common.md` in place of `{{common_rules}}`), clean the transcript
yourself (for Meet captions keep only the last, longest version of each growing caption),
and build one web page with the template's blocks in order. Publish it as an artifact.
