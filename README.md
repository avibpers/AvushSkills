# AvushSkills

Agent skills you can install on your own computer: in Claude (Code, desktop and web),
Cursor, ChatGPT, Grok and Grok Build. Each skill is one folder in [`skills/`](skills),
with its own README.

| Skill | What it does |
|---|---|
| [meeting-sum](skills/meeting-sum) | Turns any meeting transcript (Google Meet captions, Zoom/Teams subtitles, Koli, plain text) into a summary from a template: a visual brief with charts, formal board minutes, or your own. Delivers a Claude artifact, an HTML file or a Google Doc, and manages your summary templates. |

A skill is a folder with a `SKILL.md` (instructions the AI follows) and, often, scripts it runs.
Skills with scripts need **Python 3.9 or newer** on the computer where the AI runs them.

---

## Install

Pick the app you use. On a computer with several of them, the installer sets up all the ones it finds.

### Quick install (Claude Code, Cursor, Grok Build)

**Windows** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.ps1 | iex
```

**macOS / Linux**:

```bash
curl -fsSL https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.sh | bash
```

This installs every skill into the skill folders of the tools it finds:

| Tool | Folder |
|---|---|
| Claude Code | `~/.claude/skills/` |
| Cursor | `~/.cursor/skills/` (only when Claude Code isn't installed, because Cursor also reads `~/.claude/skills/`) |
| Grok Build | `~/.grok/skills/` |
| Any agent that reads `~/.agents/skills/` (Codex, Grok Build, Cursor) | `~/.agents/skills/`, on request |

To choose skills or tools, download the script and pass options:

```powershell
irm https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.ps1 -OutFile install.ps1
.\install.ps1 -Skills meeting-sum -Targets claude,cursor,grok
.\install.ps1 -List
```

```bash
curl -fsSL https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.sh | bash -s -- --skills meeting-sum --targets claude,cursor,grok
curl -fsSL https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.sh | bash -s -- --list
```

Start a new chat (or restart the app) after installing.

### Claude Code: plugin marketplace (updates built in)

```text
/plugin marketplace add avibpers/AvushSkills
/plugin install avush-skills@avush-skills
```

From a terminal: `claude plugin marketplace add avibpers/AvushSkills` and then
`claude plugin install avush-skills@avush-skills --scope user`.

Installed this way, skills are named with the plugin in front: `/avush-skills:meeting-sum`.
Use either the marketplace or the quick install, not both, or each skill shows up twice.

### Claude desktop app and claude.ai

1. Download the skill's zip from the [latest release](https://github.com/avibpers/AvushSkills/releases/latest), for example `meeting-sum.zip`.
2. In Claude, open **Customize → Skills**, press **+**, choose **Create skill → Upload a skill**, and pick the zip.
3. Turn the skill on in the list.

Skills on claude.ai run in Claude's code sandbox, so Python is already there.

### Cursor

The quick install covers Cursor. By hand: copy the skill folder to `~/.cursor/skills/<skill>/`
(or `.cursor/skills/` inside one project) and reload the window. Type `/` in the Agent chat to
pick the skill. Cursor also loads skills from `~/.claude/skills/`, so if Claude Code already has
the skill, Cursor sees it with no extra step. [Cursor docs](https://cursor.com/docs/context/skills)

### ChatGPT

1. Download the skill's zip from the [latest release](https://github.com/avibpers/AvushSkills/releases/latest).
2. In ChatGPT, open **Skills** and upload the zip from your computer. ChatGPT scans the skill
   before it can be used; some skills are held for review first.
3. On Business and Enterprise workspaces, an admin may need to allow skill uploads.

Menu names change between versions; see OpenAI's [Skills in ChatGPT](https://help.openai.com/en/articles/20001066-skills-in-chatgpt).
Parts of a skill that need tools ChatGPT doesn't have (for example Claude artifacts) are skipped,
and the skill offers its other outputs.

### Grok (grok.com and the Grok apps)

1. Download the skill's zip from the [latest release](https://github.com/avibpers/AvushSkills/releases/latest).
2. In Grok, open **Skills** and import the file (zip). You can also paste the `SKILL.md`.

Grok Skills need a paid account. See xAI's [Grok Skills announcement](https://x.ai/news/grok-skills).

### Grok Build (the Grok CLI)

The quick install covers it: skills go to `~/.grok/skills/`. Grok Build also reads Claude Code
plugin marketplaces, so you can add this repo from its **Marketplace** tab (`/plugins`).
Check what loaded with `/skills`. [Grok Build docs](https://docs.x.ai/build/features/skills-plugins-marketplaces)

---

## Update

| How you installed | How to update |
|---|---|
| Quick install, Windows | `irm https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.ps1 -OutFile install.ps1; .\install.ps1 -Update` |
| Quick install, macOS / Linux | `curl -fsSL https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.sh \| bash -s -- --update` |
| Claude Code plugin | Automatic if you turn on **auto-update** (`/plugin` → Marketplaces → avush-skills → Enable auto-update), or run `claude plugin marketplace update avush-skills` and then `claude plugin update avush-skills@avush-skills` |
| Claude desktop / claude.ai, ChatGPT, Grok web | Download the new zip from the [latest release](https://github.com/avibpers/AvushSkills/releases/latest), remove the old skill and upload the new one |
| Cloned this repo | `git pull`, then run `install.ps1` / `install.sh` from the clone |

`-Update` reinstalls the same skills in the same places it used last time (it remembers them in
`~/.avush-skills/`). Updates replace only the skill folders. Your own files, such as your meeting
templates in `~/.claude/meeting-templates/`, stay as they are.

To watch for new versions, use **Watch → Custom → Releases** on this page.

## Uninstall

```powershell
.\install.ps1 -Uninstall
```

```bash
curl -fsSL https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.sh | bash -s -- --uninstall
```

Claude Code plugin: `claude plugin uninstall avush-skills@avush-skills`. In the web apps, delete
the skill from the Skills list.

---

## Repository layout

```text
AvushSkills/
├── skills/<skill>/           one folder per skill: SKILL.md, README.md, scripts, references
├── .claude-plugin/           plugin + marketplace files (Claude Code, Grok Build)
├── install.ps1, install.sh   installers and updaters
├── tools/package.py          builds dist/<skill>.zip for upload
└── .github/workflows/        publishes the zips on every version tag
```

## Adding a skill

1. Create `skills/<name>/` with `SKILL.md` (header keys: `name` equal to the folder name, and
   `description`), a `README.md` for people, and any `scripts/` or `references/`.
2. Add a row to the table at the top of this file and a line to [CHANGELOG.md](CHANGELOG.md).
3. Check it builds: `python tools/package.py <name>`.
4. Commit, then tag a version to publish the zips: `git tag v1.2.0 && git push origin main v1.2.0`.

## License

[MIT](LICENSE)
