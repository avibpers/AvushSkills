"""The summary template collection: list, show, check, and build an AI system prompt.

A template is a Markdown file with a YAML header. The header says how the
report looks (title, date style, language, which blocks in which order, the
headings); the body is the system prompt an AI model follows to write
brief.json from a transcript. "{{common_rules}}" in a body is replaced by
templates/_common.md, so shared rules live in one place.

Templates are read from, later folders winning on the same id:
  1. <skill>/templates/                 shipped with the skill
  2. ~/.claude/meeting-templates/       the user's own collection
  3. %APPDATA%/koli/summary_templates/  (or ~/.koli/summary_templates) Koli's collection, when present

Usage:
  python templates.py list                  one line per template (JSON)
  python templates.py show <id>             header as JSON
  python templates.py prompt <id>           the full system prompt, ready for an AI model
  python templates.py check <file.md>       validates a template file
  python templates.py dirs                  the folders above, first one the user writes to
"""
import json
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
BUILTIN_DIR = SKILL_DIR / 'templates'
USER_DIR = Path.home() / '.claude' / 'meeting-templates'

# Every block the renderer knows. A template's blocks must come from this list.
BLOCKS = {
    'header': 'Title, date, and for the standard layout duration and speakers',
    'quick': 'Google Doc only: compact bottom lines (summary, decisions, actions, open, parked)',
    'tldr': 'The short summary paragraphs',
    'counts': 'Web only: number cards (decisions, actions, open questions, speakers)',
    'participants': 'Who attended, with roles',
    'agenda': 'Numbered list of agenda items',
    'agenda_details': 'Per agenda item: discussion, decisions, action items',
    'decisions': 'All decisions as a list',
    'action_items': 'All action items as a table',
    'lists': 'Open questions and parked items side by side',
    'open_questions': 'Open questions only',
    'parked': 'Parked items only',
    'next_meeting': 'Points left for the next meeting',
    'speakers': 'Who spoke: talk-time charts and a table with roles',
    'screenshots': 'What was on screen (Koli meetings only; empty here)',
    'topics': 'Topic cards in time order with points and quotes',
    'sections': 'Custom sections the template defines (title + bullets or paragraphs)',
    'notes': 'Notes on transcript quality',
    'transcript': 'The full transcript',
    'data': 'Web only: the brief as JSON for AI tools',
    'page_break': 'Google Doc only: start a new page',
}


def koli_dir() -> Path:
    base = os.environ.get('APPDATA')
    return (Path(base) / 'koli' if base else Path.home() / '.koli') / 'summary_templates'


def dirs() -> list:
    return [BUILTIN_DIR, USER_DIR, koli_dir()]


# ── Reading a template file ──────────────────────────────────────────────────

def _scalar(text: str):
    text = text.strip()
    if text == '':
        return None
    if text[0] in '"\'' and text[-1] == text[0]:
        return text[1:-1]
    if text in ('true', 'false'):
        return text == 'true'
    if text in ('null', '~'):
        return None
    if re.fullmatch(r'-?\d+', text):
        return int(text)
    if text.startswith('[') and text.endswith(']'):
        inner = text[1:-1]
        return [_scalar(p) for p in re.findall(r'"[^"]*"|\'[^\']*\'|[^,]+', inner) if p.strip()]
    return text


def _mini_yaml(text: str) -> dict:
    # Enough YAML for template headers when PyYAML isn't installed:
    # key: value, inline [lists], and one level of indented maps or "- item" lists.
    out, parent = {}, None
    for line in text.split('\n'):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if line.startswith((' ', '\t')) and parent is not None:
            item = line.strip()
            if item.startswith('- '):
                if not isinstance(out[parent], list):
                    out[parent] = []
                out[parent].append(_scalar(item[2:]))
            elif ':' in item:
                if not isinstance(out[parent], dict):
                    out[parent] = {}
                k, v = item.split(':', 1)
                out[parent][k.strip()] = _scalar(v)
            continue
        k, v = line.split(':', 1)
        out[k.strip()] = _scalar(v)
        parent = k.strip() if out[k.strip()] is None else None
    return out


def parse(path: Path) -> dict:
    text = path.read_text(encoding='utf-8')
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', text, re.S)
    if not m:
        raise ValueError(f'{path.name}: no YAML header between --- lines')
    try:
        import yaml
        head = yaml.safe_load(m.group(1)) or {}
    except ImportError:
        head = _mini_yaml(m.group(1))
    head['body'] = m.group(2).strip()
    head['file'] = str(path)
    head.setdefault('id', path.stem)
    return head


def collection() -> dict:
    found = {}
    for d in dirs():
        if d.is_dir():
            for f in sorted(d.glob('*.md')):
                if f.name.startswith('_'):
                    continue
                try:
                    t = parse(f)
                except ValueError:
                    continue
                t['origin'] = 'built-in' if d == BUILTIN_DIR else ('koli' if d == koli_dir() else 'mine')
                found[t['id']] = t
    return found


def get(template_id_or_path: str) -> dict:
    p = Path(template_id_or_path)
    if p.suffix == '.md' and p.exists():
        return parse(p)
    found = collection()
    if template_id_or_path not in found:
        raise SystemExit(f"No template '{template_id_or_path}'. Known: {', '.join(found)}")
    return found[template_id_or_path]


def _common() -> str:
    for d in reversed(dirs()):
        f = d / '_common.md'
        if f.exists():
            return f.read_text(encoding='utf-8').strip()
    return ''


def prompt(t: dict) -> str:
    # The system prompt: the template body with the shared rules filled in, and
    # the language rule the template sets.
    body = t['body'].replace('{{common_rules}}', _common())
    lang = t.get('language') or 'meeting'
    rule = ('Write the report in the language most of the meeting was spoken in, unless the user asks for another.'
            if lang == 'meeting' else f'Write the report in this language: {lang}, unless the user asks for another.')
    return f"{body}\n\n## Language\n\n{rule} Set \"language\" in the JSON to the ISO code you wrote in."


def check(t: dict) -> list:
    problems = []
    for key in ('id', 'name', 'description', 'blocks'):
        if not t.get(key):
            problems.append(f'missing "{key}" in the header')
    if t.get('id') and not re.fullmatch(r'[a-z0-9][a-z0-9-]*', str(t['id'])):
        problems.append('"id" must be lowercase letters, digits and hyphens')
    for key in ('blocks', 'doc_blocks'):
        for b in t.get(key) or []:
            if b not in BLOCKS:
                problems.append(f'unknown block "{b}" in {key}; known: {", ".join(BLOCKS)}')
    title = t.get('title') or {}
    if isinstance(title, dict) and title.get('mode') == 'fixed' and not title.get('choices'):
        problems.append('a fixed title needs "choices"')
    if t.get('date') not in (None, 'date', 'datetime'):
        problems.append('"date" must be date or datetime')
    if '```json' not in t.get('body', ''):
        problems.append('the body should show the JSON shape the AI must return in a ```json block')
    return problems


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'list'
    if cmd == 'list':
        for t in collection().values():
            print(json.dumps({'id': t['id'], 'name': t.get('name'), 'description': t.get('description'),
                              'language': t.get('language') or 'meeting', 'origin': t['origin'], 'file': t['file']},
                             ensure_ascii=False))
    elif cmd == 'show':
        t = get(sys.argv[2])
        print(json.dumps({k: v for k, v in t.items() if k != 'body'}, ensure_ascii=False, indent=1))
    elif cmd == 'prompt':
        print(prompt(get(sys.argv[2])))
    elif cmd == 'check':
        t = parse(Path(sys.argv[2]))
        problems = check(t)
        print('\n'.join(problems) if problems else f"OK: {t['id']} ({t.get('name')})")
        sys.exit(1 if problems else 0)
    elif cmd == 'dirs':
        for d in dirs()[1:] + dirs()[:1]:
            print(d)
    else:
        sys.exit(__doc__)
