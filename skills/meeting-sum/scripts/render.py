"""Renders a meeting summary from brief.json + transcript.json, laid out by a template.

  python render.py brief.json transcript.json [--template <id or file.md>]
        --html out.html        web page (local file or Claude artifact)
        --gdoc out.html        HTML that Google Drive converts to a Google Doc
        [--no-transcript]      leave the transcript out of the Google Doc

The template (default: the brief's "template" field, else "standard") picks the
blocks and their order, the headings, the title style and the date style; see
templates.py for the block list. The web page is one self-contained file that
follows the Claude artifact page contract (title, colour tokens, light and dark
themes, phone width), so it can be published as is. The Google Doc version
uses headings, lists, tables and page breaks; its charts are coloured text bars.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import templates  # noqa: E402

# Speaker colours by speaker order, readable on light and dark backgrounds.
COLOURS = ['#2A78D6', '#EB6834', '#1BAF7A', '#8B5CF6', '#D6336C', '#B7860B', '#0E8A9B', '#7A8594']
STATUS = {'do_now': 'Do now', 'plan_only': 'Plan only', 'waiting': 'Waiting', 'done': 'Done'}
RTL_LANGS = ('he', 'ar', 'fa', 'ur', 'yi')
WEB_ONLY = ('counts', 'data')
DOC_ONLY = ('quick', 'page_break')
LABELS = {
    'tldr': 'In short', 'quick': 'Quick summary', 'decisions': 'Decisions', 'action_items': 'Action items',
    'open_questions': 'Open questions', 'parked': 'Parked for later', 'speakers': 'Who spoke',
    'topics': 'How the meeting went', 'participants': 'Participants', 'agenda': 'Meeting Agenda',
    'agenda_details': 'Key Points, Decisions, and Action Items', 'agenda_discussion': 'Discussion',
    'agenda_decisions': 'Decisions', 'agenda_actions': 'Action items',
    'next_meeting': 'Points for the next meeting', 'transcript': 'Full transcript', 'data': 'Data for AI tools',
    'notes': 'Notes on the transcript', 'owner': 'Owner', 'due': 'Due', 'status': 'Status', 'task': 'Task',
}
e = html.escape


# ── Numbers and words both outputs share ─────────────────────────────────────

def clock(seconds) -> str:
    s = max(0, int(seconds or 0))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def lang_of(tr: dict) -> str:
    sample = ' '.join(t['text'] for t in tr['turns'][:40])
    return 'he' if len(re.findall(r'[֐-׿]', sample)) > len(sample) / 4 else ''


class Ctx:
    """Everything a block needs: the brief, the transcript, the template and derived numbers."""

    def __init__(self, brief: dict, tr: dict, tpl: dict):
        self.brief, self.tr, self.tpl = brief, tr, tpl
        names, roles = brief.get('participants') or {}, brief.get('roles') or {}
        self.people = [{'id': sp['id'], 'name': names.get(sp['id']) or sp['name'], 'role': roles.get(sp['id'], ''),
                        'colour': COLOURS[i % len(COLOURS)]} for i, sp in enumerate(tr['speakers'])]
        self.by_id = {p['id']: p for p in self.people}
        self.stats = self._talk_stats()
        self.rtl = (brief.get('language') or '').lower()[:2] in RTL_LANGS
        self.turn_dir = 'rtl' if lang_of(tr) == 'he' else 'auto'
        self.topics = sorted(brief.get('topics') or [], key=lambda t: t.get('start') or 0)

    def label(self, key: str) -> str:
        return ((self.brief.get('labels') or {}).get(key) or (self.tpl.get('labels') or {}).get(key)
                or LABELS.get(key, key))

    @property
    def title(self) -> str:
        spec = self.tpl.get('title') or {}
        if isinstance(spec, dict) and spec.get('mode') == 'fixed':
            choices = spec.get('choices') or ['Meeting Summary']
            return self.brief.get('title') if self.brief.get('title') in choices else choices[0]
        return self.brief.get('title') or self.tr.get('title') or 'Meeting summary'

    @property
    def date(self) -> str:
        d = str(self.brief.get('date') or self.tr.get('date') or '')
        return d[:10] if self.tpl.get('date') == 'date' else d.replace('T', ' ')[:16]

    def meta(self) -> str:
        if self.tpl.get('date') == 'date':
            return self.date
        approx = '~' if self.tr.get('timing') == 'estimated' else ''
        parts = [self.date, f"{approx}{clock(self.tr.get('duration_s'))}", ', '.join(p['name'] for p in self.people)]
        return ' · '.join(p for p in parts if p)

    def stamp(self, sec) -> str:
        if sec is None:
            return ''
        return ('~' if self.tr.get('timing') == 'estimated' else '') + clock(sec)

    def turn_index(self, sec) -> int:
        best = 0
        for i, t in enumerate(self.tr['turns']):
            if t['start'] <= (sec or 0) + 0.5:
                best = i
        return best

    def person(self, name):
        # A participant whose first name matches an owner's name, if any.
        if not name:
            return None
        first = str(name).split()[0].lower()
        return next((p for p in self.people if p['name'].split()[0].lower() == first), None)

    # Decisions and actions may live at the top level or inside agenda items.
    def decisions(self) -> list:
        return self.brief.get('decisions') or [d for a in self.brief.get('agenda') or [] for d in a.get('decisions') or []]

    def actions(self) -> list:
        return self.brief.get('action_items') or [x for a in self.brief.get('agenda') or [] for x in a.get('action_items') or []]

    def attendees(self) -> list:
        listed = self.brief.get('attendees')
        if listed:
            return [a if isinstance(a, dict) else {'name': str(a)} for a in listed]
        return [{'name': p['name'], 'role': p['role']} for p in self.people]

    def _talk_stats(self) -> list:
        by = {p['id']: dict(p, seconds=0.0, turns=0, words=0) for p in self.people}
        for t in self.tr['turns']:
            s = by[t['speaker']]
            s['seconds'] += max(t['end'] - t['start'], 0)
            s['turns'] += 1
            s['words'] += len(re.findall(r'\w+', t['text']))
        total = sum(s['seconds'] for s in by.values()) or 1
        for s in by.values():
            s['share'] = s['seconds'] / total
        return sorted(by.values(), key=lambda s: -s['seconds'])

    def buckets(self):
        # Seconds each speaker talked in each slice of the meeting, at most 40 slices.
        length = max((t['end'] for t in self.tr['turns']), default=0)
        size = 60
        while length / size > 40:
            size *= 2 if size < 600 else 1.5
        size = int(size)
        n = int(length // size) + 1
        rows = [{p['id']: 0.0 for p in self.people} for _ in range(n)]
        for t in self.tr['turns']:
            a, b, i = t['start'], t['end'], int(t['start'] // size)
            while a < b and i < n:
                hi = min(b, (i + 1) * size)
                rows[i][t['speaker']] += hi - a
                a, i = hi, i + 1
        return size, rows


# ── The web page ─────────────────────────────────────────────────────────────

CSS = """
:root {
  --bg: #f6f7f9; --surface: #ffffff; --fg: #15202b; --fg-2: #4b5765; --fg-3: #737e8c;
  --line: #dde2e8; --accent: #1f5fa8; --accent-soft: #e6eef9;
  --ok: #1a7f37; --ok-soft: #e3f3e8; --warn: #9a6700; --warn-soft: #fff4d6;
  --info: #0b6b8a; --info-soft: #e0f2f7; --mute: #6e7781; --mute-soft: #eceff3;
  --font-body: 'Heebo', 'Segoe UI', Arial, sans-serif; --font-mono: 'IBM Plex Mono', Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #121619; --surface: #1a2026; --fg: #e8ecf0; --fg-2: #b4bcc6; --fg-3: #8b96a2;
  --line: #2b343d; --accent: #6ea8ea; --accent-soft: #1d2a3b;
  --ok: #57c279; --ok-soft: #16301f; --warn: #e3b341; --warn-soft: #3a2e10;
  --info: #5cc3e0; --info-soft: #12303a; --mute: #9aa4ae; --mute-soft: #262d35; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #121619; --surface: #1a2026; --fg: #e8ecf0; --fg-2: #b4bcc6; --fg-3: #8b96a2;
  --line: #2b343d; --accent: #6ea8ea; --accent-soft: #1d2a3b;
  --ok: #57c279; --ok-soft: #16301f; --warn: #e3b341; --warn-soft: #3a2e10;
  --info: #5cc3e0; --info-soft: #12303a; --mute: #9aa4ae; --mute-soft: #262d35; color-scheme: dark }
* { box-sizing: border-box }
body { background: var(--bg); color: var(--fg); font-family: var(--font-body); font-size: 15px; line-height: 1.55;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 28px 72px }
.wrap { max-width: 1040px; margin: 0 auto; display: grid; gap: 40px }
h1, h2, h3 { text-wrap: balance; margin: 0; line-height: 1.2 }
h1 { font-size: clamp(1.6rem, 4vw, 2.2rem); font-weight: 800; letter-spacing: -0.01em }
h2 { font-size: 1.2rem; font-weight: 700; display: flex; align-items: baseline; gap: 10px }
h2 .count { font-size: .8rem; color: var(--fg-3); font-weight: 500 }
h3 { font-size: 1rem; font-weight: 700 }
p { margin: 0 }
section { display: grid; gap: 14px; min-width: 0 }
header { display: grid; gap: 10px }
.eyebrow { font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; color: var(--fg-3); font-weight: 500 }
.meta { color: var(--fg-2); font-size: .92rem }
.num, .ts { font-family: var(--font-mono); font-variant-numeric: tabular-nums }
.tldr { font-size: 1.08rem; max-width: 70ch; border-inline-start: 3px solid var(--accent); padding-inline-start: 16px; display: grid; gap: 8px }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; display: grid; gap: 2px }
.card b { font-size: 1.6rem; font-weight: 800 }
.card span { color: var(--fg-3); font-size: .85rem }
ol.list, ul.list { margin: 0; padding-inline-start: 0; list-style: none; display: grid; gap: 8px }
.list li { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 10px 14px; display: flex; gap: 12px; align-items: baseline }
.list li .id { font-family: var(--font-mono); color: var(--fg-3); font-size: .8rem; min-width: 2.2em }
.list li .tx { flex: 1; min-width: 0 }
a.t { color: var(--accent); text-decoration: none; font-family: var(--font-mono); font-size: .8rem; white-space: nowrap }
a.t:hover { text-decoration: underline }
.chip { display: inline-flex; align-items: center; gap: 5px; padding: 1px 9px; border-radius: 999px; font-size: .74rem; font-weight: 500; white-space: nowrap }
.chip::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor }
.chip.do_now { background: var(--ok-soft); color: var(--ok) } .chip.plan_only { background: var(--warn-soft); color: var(--warn) }
.chip.waiting { background: var(--info-soft); color: var(--info) } .chip.done { background: var(--mute-soft); color: var(--mute) }
.who { display: inline-flex; align-items: center; gap: 6px; font-weight: 500; white-space: nowrap }
.who i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; background: var(--line) }
.tablewrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface) }
table { border-collapse: collapse; width: 100%; font-size: .92rem }
th, td { text-align: start; padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top }
th { font-size: .74rem; text-transform: uppercase; letter-spacing: .06em; color: var(--fg-3); font-weight: 500 }
tr:last-child td { border-bottom: 0 }
.split { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px }
.charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px; display: grid; gap: 10px; min-width: 0 }
.panel svg { width: 100%; height: auto; display: block }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: .85rem }
.note { color: var(--fg-3); font-size: .85rem }
details.topic { background: var(--surface); border: 1px solid var(--line); border-radius: 10px }
details.topic > summary { cursor: pointer; padding: 12px 16px; display: flex; gap: 12px; align-items: baseline; list-style: none }
details.topic > summary::-webkit-details-marker { display: none }
details.topic > summary::before { content: "▸"; color: var(--fg-3); transition: transform .15s }
details.topic[open] > summary::before { transform: rotate(90deg) }
details.topic .lead { color: var(--fg-2); font-size: .9rem }
details.topic .body { padding: 0 16px 16px 40px; display: grid; gap: 10px }
details.topic ul { margin: 0; padding-inline-start: 18px; display: grid; gap: 4px }
blockquote { margin: 0; border-inline-start: 3px solid var(--line); padding: 4px 12px; color: var(--fg-2) }
blockquote .by { display: block; font-size: .8rem; color: var(--fg-3); margin-top: 2px }
.filters { display: flex; flex-wrap: wrap; gap: 8px }
.btn { font: inherit; font-size: .85rem; border: 1px solid var(--line); background: var(--surface); color: var(--fg); border-radius: 999px; padding: 4px 12px; cursor: pointer }
.btn[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); color: var(--accent) }
details.transcript > summary { cursor: pointer; font-weight: 700; font-size: 1.2rem }
.turns { display: grid; gap: 2px; margin-top: 12px; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 8px }
.turn { display: grid; grid-template-columns: 4.2em 8em 1fr; gap: 10px; padding: 6px 8px; border-radius: 6px }
.turn:target { background: var(--accent-soft) }
.turn .ts { color: var(--fg-3); font-size: .78rem; padding-top: 2px }
.turn .sp { font-weight: 600; font-size: .88rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.turn .tx { min-width: 0; overflow-wrap: anywhere }
.topicrow { padding: 10px 8px 4px; font-weight: 700; color: var(--fg-2); font-size: .85rem; border-top: 1px dashed var(--line); margin-top: 6px }
pre.json { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px; overflow: auto; max-height: 420px; font-family: var(--font-mono); font-size: .78rem; margin: 0 }
.row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap }
@media (max-width: 560px) { .turn { grid-template-columns: 1fr; gap: 0 } details.topic .body { padding-left: 16px } }
"""

CSS += """
.people { display: flex; flex-wrap: wrap; gap: 8px }
.people .p { background: var(--surface); border: 1px solid var(--line); border-radius: 999px; padding: 4px 14px; font-size: .92rem }
.people .p span { color: var(--fg-3) }
.items { display: grid; gap: 14px }
.item { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; display: grid; gap: 10px }
.item h3 { display: flex; gap: 10px; align-items: baseline }
.item h3 .n { font-family: var(--font-mono); color: var(--accent) }
.item h4 { margin: 0; font-size: .74rem; text-transform: uppercase; letter-spacing: .06em; color: var(--fg-3); font-weight: 500 }
.item ul { margin: 0; padding-inline-start: 18px; display: grid; gap: 4px }
.item .grp { display: grid; gap: 4px }
ol.agenda { margin: 0; padding-inline-start: 22px; display: grid; gap: 6px; font-size: 1.02rem }
.custom ul { margin: 0; padding-inline-start: 18px; display: grid; gap: 4px }
"""

JS = """
(function () {
  var box = document.getElementById('turns');
  if (box) document.querySelectorAll('.filters .btn').forEach(function (b, _, all) {
    b.addEventListener('click', function () {
      all.forEach(function (o) { o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); });
      box.querySelectorAll('.turn').forEach(function (el) { el.hidden = b.dataset.sp !== 'all' && el.dataset.sp !== b.dataset.sp; });
      box.querySelectorAll('.topicrow').forEach(function (el) { el.hidden = b.dataset.sp !== 'all'; });
    });
  });
  var tbox = document.getElementById('transcript-box');
  function openTranscript() { if (tbox) tbox.open = true; }
  document.querySelectorAll('a.t').forEach(function (a) { a.addEventListener('click', openTranscript); });
  if (/^#t\\d+$/.test(location.hash)) { openTranscript(); }
  var view = document.getElementById('json-view'), toast = document.getElementById('toast'), copy = document.getElementById('copy-json');
  if (copy) copy.addEventListener('click', function () {
    function fallback() { var r = document.createRange(); r.selectNodeContents(view); var s = getSelection(); s.removeAllRanges(); s.addRange(r); toast.textContent = 'Selected, press Ctrl+C'; toast.hidden = false; }
    try { navigator.clipboard.writeText(view.textContent).then(function () { toast.textContent = 'Copied'; toast.hidden = false; setTimeout(function () { toast.hidden = true; }, 2000); }, fallback); }
    catch (err) { fallback(); }
  });
})();
"""


def w_link(c: Ctx, sec) -> str:
    # A time that jumps to the transcript, or plain text when the page has none.
    if sec is None:
        return ''
    if 'transcript' not in c.tpl['blocks']:
        return f"<span class='t num note'>{c.stamp(sec)}</span>"
    return f"<a class='t' href='#t{c.turn_index(sec)}'>{c.stamp(sec)}</a>"


def w_who(p: dict) -> str:
    return f"<span class='who'><i style='background:{p['colour']}'></i>{e(p['name'])}</span>"


def w_list(c: Ctx, key: str, items: list) -> str:
    if not items:
        return ''
    rows = ''.join(f"<li><span class='id'>{e(str(x.get('id', '')))}</span><span class='tx'>{e(x['text'])}</span>{w_link(c, x.get('at'))}</li>"
                   for x in items)
    return f"<section><h2>{e(c.label(key))} <span class='count'>{len(items)}</span></h2><ul class='list'>{rows}</ul></section>"


def w_actions_table(c: Ctx, items: list) -> str:
    rows = []
    for a in items:
        p = c.person(a.get('owner'))
        owner = w_who(p) if p else (e(a['owner']) if a.get('owner') else "<span class='note'>Not set</span>")
        status = a.get('status') or 'do_now'
        effort = f"<br><span class='note'>{e(a['effort'])}</span>" if a.get('effort') else ''
        rows.append(f"<tr><td class='num'>{e(str(a.get('id', '')))}</td><td>{e(a['task'])}{effort}</td><td>{owner}</td>"
                    f"<td><span class='chip {e(status)}'>{e(STATUS.get(status, status))}</span></td>"
                    f"<td>{e(a.get('due') or '—')}</td><td>{w_link(c, a.get('at'))}</td></tr>")
    return (f"<div class='tablewrap'><table><tr><th>#</th><th>{e(c.label('task'))}</th><th>{e(c.label('owner'))}</th>"
            f"<th>{e(c.label('status'))}</th><th>{e(c.label('due'))}</th><th></th></tr>{''.join(rows)}</table></div>")


def w_share_svg(c: Ctx) -> str:
    w, left, right = 360, 96, 92
    h = len(c.stats) * 32 + 8
    top = max(s['seconds'] for s in c.stats) or 1
    out = [f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='Talk time by speaker'>"]
    for i, s in enumerate(c.stats):
        y, bw = 6 + i * 32, max((w - left - right) * s['seconds'] / top, 2)
        lab = f"{c.stamp(s['seconds'])} · {round(s['share'] * 100)}%"
        out.append(f"<text x='{left - 8}' y='{y + 15}' text-anchor='end' font-size='12' fill='var(--fg-2)'>{e(s['name'][:14])}</text>"
                   f"<rect x='{left}' y='{y}' width='{bw:.1f}' height='20' rx='4' fill='{s['colour']}'>"
                   f"<title>{e(s['name'])}: {lab}, {s['turns']} turns, {s['words']} words</title></rect>"
                   f"<text x='{left + bw + 6:.1f}' y='{y + 15}' font-size='11' fill='var(--fg-2)' font-family='monospace'>{lab}</text>")
    return ''.join(out) + '</svg>'


def w_timeline_svg(c: Ctx):
    size, rows = c.buckets()
    W, H, padL, padB, padT = 560, 200, 36, 24, 8
    plotW, plotH = W - padL - 8, H - padT - padB
    col = plotW / max(len(rows), 1)
    top = max((sum(r.values()) for r in rows), default=1) or 1
    out = [f"<svg viewBox='0 0 {W} {H}' role='img' aria-label='Who talked over time'>"]
    for g in (0, .5, 1):
        y = padT + plotH - plotH * g
        out.append(f"<line x1='{padL}' x2='{W - 8}' y1='{y:.1f}' y2='{y:.1f}' stroke='var(--line)'/>"
                   f"<text x='{padL - 5}' y='{y + 4:.1f}' text-anchor='end' font-size='9' fill='var(--fg-3)' font-family='monospace'>{round(top * g)}s</text>")
    for i, r in enumerate(rows):
        x, y = padL + i * col + 1, padT + plotH
        tip = [f"{c.stamp(i * size)}–{c.stamp((i + 1) * size)}"]
        for p in c.people:
            v = r[p['id']]
            if v <= 0:
                continue
            h = plotH * v / top
            y -= h
            out.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{max(col - 2, 1):.1f}' height='{max(h - 1, .5):.1f}' fill='{p['colour']}'/>")
            tip.append(f"{p['name']}: {round(v)}s")
        out.append(f"<rect x='{padL + i * col:.1f}' y='{padT}' width='{col:.1f}' height='{plotH}' fill='transparent'><title>{e(chr(10).join(tip))}</title></rect>")
        if i % max(1, len(rows) // 6) == 0:
            out.append(f"<text x='{padL + i * col + col / 2:.1f}' y='{H - 8}' text-anchor='middle' font-size='9' fill='var(--fg-3)' font-family='monospace'>{c.stamp(i * size)}</text>")
    return ''.join(out) + '</svg>', size


# Each web block returns its HTML, or '' when the brief has nothing for it.

def wb_header(c):
    return (f"<header><span class='eyebrow'>Meeting summary</span><h1>{e(c.title)}</h1>"
            f"<p class='meta'>{e(c.meta())}</p></header>")


def wb_tldr(c):
    paras = c.brief.get('tldr') or []
    return (f"<section><h2>{e(c.label('tldr'))}</h2><div class='tldr'>" + ''.join(f"<p>{e(p)}</p>" for p in paras)
            + "</div></section>") if paras else ''


def wb_counts(c):
    counts = [(len(c.decisions()), 'decisions'), (len(c.actions()), 'action items'),
              (len(c.brief.get('open_questions') or []), 'open questions'), (len(c.people), 'speakers')]
    return "<div class='cards'>" + ''.join(f"<div class='card'><b class='num'>{n}</b><span>{lbl}</span></div>" for n, lbl in counts) + "</div>"


def wb_decisions(c):
    return w_list(c, 'decisions', c.decisions())


def wb_action_items(c):
    items = c.actions()
    if not items:
        return ''
    note = "<p class='note'>No deadlines were stated in the meeting.</p>" if all(not a.get('due') for a in items) else ''
    return f"<section><h2>{e(c.label('action_items'))} <span class='count'>{len(items)}</span></h2>{w_actions_table(c, items)}{note}</section>"


def wb_open_questions(c):
    return w_list(c, 'open_questions', c.brief.get('open_questions') or [])


def wb_parked(c):
    return w_list(c, 'parked', c.brief.get('parked') or [])


def wb_lists(c):
    inner = wb_open_questions(c) + wb_parked(c)
    return f"<div class='split'>{inner}</div>" if inner else ''


def wb_next_meeting(c):
    return w_list(c, 'next_meeting', c.brief.get('next_meeting') or [])


def wb_participants(c):
    people = c.attendees()
    chips = ''.join(f"<span class='p'>{e(a['name'])}{(' <span>· ' + e(a['role']) + '</span>') if a.get('role') else ''}</span>" for a in people)
    return f"<section><h2>{e(c.label('participants'))}</h2><div class='people'>{chips}</div></section>" if people else ''


def wb_agenda(c):
    items = c.brief.get('agenda') or []
    if not items:
        return ''
    return (f"<section><h2>{e(c.label('agenda'))}</h2><ol class='agenda'>"
            + ''.join(f"<li>{e(a['title'])}</li>" for a in items) + "</ol></section>")


def wb_agenda_details(c):
    items = c.brief.get('agenda') or []
    if not items:
        return ''
    cards = []
    for n, a in enumerate(items, 1):
        parts = []
        if a.get('discussion'):
            parts.append(f"<div class='grp'><h4>{e(c.label('agenda_discussion'))}</h4><ul>" + ''.join(f"<li>{e(x)}</li>" for x in a['discussion']) + "</ul></div>")
        if a.get('decisions'):
            parts.append(f"<div class='grp'><h4>{e(c.label('agenda_decisions'))}</h4><ul>" + ''.join(f"<li>{e(d['text'])} {w_link(c, d.get('at'))}</li>" for d in a['decisions']) + "</ul></div>")
        if a.get('action_items'):
            parts.append(f"<div class='grp'><h4>{e(c.label('agenda_actions'))}</h4>{w_actions_table(c, a['action_items'])}</div>")
        cards.append(f"<article class='item'><h3><span class='n'>{n}.</span>{e(a['title'])}</h3>{''.join(parts)}</article>")
    return f"<section><h2>{e(c.label('agenda_details'))}</h2><div class='items'>{''.join(cards)}</div></section>"


def wb_speakers(c):
    tl, size = w_timeline_svg(c)
    unit = 'minute' if size == 60 else f"{size // 60} minutes"
    est = " Times are estimated from word counts, because the transcript had none." if c.tr.get('timing') == 'estimated' else ''
    rows = ''.join(f"<tr><td>{w_who(s)}</td><td class='num'>{c.stamp(s['seconds'])}</td><td class='num'>{round(s['share'] * 100)}%</td>"
                   f"<td class='num'>{s['turns']}</td><td>{e(s['role'])}</td></tr>" for s in c.stats)
    return (f"<section><h2>{e(c.label('speakers'))}</h2><div class='charts'>"
            f"<div class='panel'><h3>Talk time</h3>{w_share_svg(c)}</div>"
            f"<div class='panel'><h3>Over the meeting</h3>{tl}<div class='legend'>{''.join(w_who(p) for p in c.people)}</div>"
            f"<p class='note'>Seconds spoken in each {unit}. Hover a bar for details.{est}</p></div></div>"
            "<div class='tablewrap'><table><tr><th>Speaker</th><th>Talk time</th><th>Share</th><th>Turns</th><th>Role in this meeting</th></tr>"
            f"{rows}</table></div></section>")


def wb_topics(c):
    if not c.topics:
        return ''
    out = [f"<section><h2>{e(c.label('topics'))} <span class='count'>{len(c.topics)} topics</span></h2>"]
    for t in c.topics:
        lead_by = c.by_id.get(t.get('led_by'))
        body = "<ul>" + ''.join(f"<li>{e(p)}</li>" for p in t.get('points') or []) + "</ul>" if t.get('points') else ''
        for q in t.get('quotes') or []:
            body += f"<blockquote dir='auto'>“{e(q['text'])}”<span class='by'>{e(q.get('who') or '')} {w_link(c, q.get('at'))}</span></blockquote>"
        if 'transcript' in c.tpl['blocks']:
            body += f"<p>{w_link(c, t.get('start'))} <span class='note'>jump to this part of the transcript</span></p>"
        out.append(f"<details class='topic'><summary><span class='num note'>{c.stamp(t.get('start'))}</span>"
                   f"<span><h3>{e(t['title'])}</h3><span class='lead'>{e(t.get('lead') or '')}</span></span>"
                   f"{w_who(lead_by) if lead_by else ''}</summary><div class='body'>{body}</div></details>")
    return ''.join(out) + "</section>"


def wb_sections(c):
    out = []
    for s in c.brief.get('sections') or []:
        body = ''.join(f"<p>{e(p)}</p>" for p in s.get('text') or [])
        if s.get('items'):
            body += "<ul>" + ''.join(f"<li>{e(x)}</li>" for x in s['items']) + "</ul>"
        out.append(f"<section class='custom'><h2>{e(s['title'])}</h2>{body}</section>")
    return ''.join(out)


def wb_notes(c):
    notes = c.brief.get('notes') or []
    return f"<p class='note'>{e(c.label('notes'))}: {e('; '.join(notes))}</p>" if notes else ''


def wb_transcript(c):
    rows, ti = [], 0
    for i, t in enumerate(c.tr['turns']):
        while ti < len(c.topics) and (c.topics[ti].get('start') or 0) <= t['start']:
            rows.append(f"<div class='topicrow'>{e(c.topics[ti]['title'])}</div>")
            ti += 1
        p = c.by_id[t['speaker']]
        rows.append(f"<div class='turn' id='t{i}' data-sp='{e(p['id'])}'><span class='ts'>{c.stamp(t['start'])}</span>"
                    f"<span class='sp' style='color:{p['colour']}'>{e(p['name'])}</span><span class='tx' dir='{c.turn_dir}'>{e(t['text'])}</span></div>")
    buttons = "<button class='btn' data-sp='all' aria-pressed='true'>Everyone</button>" + ''.join(
        f"<button class='btn' data-sp='{e(p['id'])}' aria-pressed='false'>{e(p['name'])}</button>" for p in c.people)
    return (f"<section><details class='transcript' id='transcript-box'><summary>{e(c.label('transcript'))} "
            f"<span class='count note'>{len(c.tr['turns'])} turns · {c.tr.get('words', 0)} words</span></summary>"
            f"<div class='filters' style='margin-top:12px'>{buttons}</div><div class='turns' id='turns'>{''.join(rows)}</div></details></section>")


def wb_data(c):
    data = json.dumps(c.brief, ensure_ascii=False, indent=2)
    return (f"<section><h2>{e(c.label('data'))}</h2><p class='note'>The same summary as JSON, for other AI tools. Times are in seconds from the start.</p>"
            "<div class='row'><button class='btn' id='copy-json' type='button'>Copy JSON</button><span class='note' id='toast' hidden>Copied</span></div>"
            f"<pre class='json' id='json-view' dir='ltr'>{e(data)}</pre></section>")


def page_html(c: Ctx) -> str:
    head = ["<meta charset='utf-8'>", f"<title>{e(c.title[:60])}</title>",
            "<meta name='claude:viewport-fit-sides' content='cover'>",
            "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap'>",
            f"<style>{CSS}</style>", f"<div class='wrap' dir='{'rtl' if c.rtl else 'ltr'}'>"]
    body = [globals()['wb_' + b](c) for b in c.tpl['blocks'] if b not in DOC_ONLY]
    return '\n'.join(head + [b for b in body if b] + [f"</div><script>{JS}</script>"])


# ── The Google Doc version ───────────────────────────────────────────────────
# Google Docs keeps headings, lists, tables, colours and page breaks from HTML.
# Charts are rows of coloured block characters, so no images are needed.

GREY = "style='color:#6b7280'"
TABLE = "border='1' cellpadding='5' style='border-collapse:collapse'"


def d_at(c, sec):
    return f" <span {GREY}>({c.stamp(sec)})</span>" if sec is not None else ''


def d_bar(n: int, colour: str) -> str:
    return f"<span style='color:{colour}'>{'█' * max(n, 0)}</span>"


def d_list(c, key, items, numbered=False):
    if not items:
        return ''
    tag = 'ol' if numbered else 'ul'
    return f"<h2>{e(c.label(key))}</h2><{tag}>" + ''.join(f"<li>{e(x['text'])}{d_at(c, x.get('at'))}</li>" for x in items) + f"</{tag}>"


def d_actions(c, items):
    rows = ''.join(f"<tr><td>{e(str(a.get('id', '')))}</td><td>{e(a['task'])}</td><td>{e(a.get('owner') or 'Not set')}</td>"
                   f"<td>{e(STATUS.get(a.get('status'), a.get('status') or ''))}</td><td>{e(a.get('due') or '—')}</td></tr>" for a in items)
    return (f"<table {TABLE}><tr><th>#</th><th>{e(c.label('task'))}</th><th>{e(c.label('owner'))}</th>"
            f"<th>{e(c.label('status'))}</th><th>{e(c.label('due'))}</th></tr>{rows}</table>")


def db_header(c):
    return f"<h1>{e(c.title)}</h1><p {GREY}>{e(c.meta())}</p>"


def db_page_break(c):
    return "<p style='page-break-before:always'></p>"


def db_quick(c):
    b = c.brief
    out = [f"<h2>{e(c.label('quick'))}</h2>"] + [f"<p>{e(p)}</p>" for p in b.get('tldr') or []]
    if c.decisions():
        out += [f"<h3>{e(c.label('decisions'))}</h3><ul>"] + [f"<li>{e(d['text'])}</li>" for d in c.decisions()] + ["</ul>"]
    if c.actions():
        out.append(f"<h3>{e(c.label('action_items'))}</h3><ul>")
        out += [f"<li>{e(a['task'])} · <b>{e(a.get('owner') or 'Owner not set')}</b> · {e(STATUS.get(a.get('status'), a.get('status') or ''))}"
                f"{(' · due ' + e(a['due'])) if a.get('due') else ''}</li>" for a in c.actions()]
        out.append("</ul>")
    for key in ('open_questions', 'parked'):
        if b.get(key):
            out += [f"<h3>{e(c.label(key))}</h3><ul>"] + [f"<li>{e(x['text'])}</li>" for x in b[key]] + ["</ul>"]
    return ''.join(out)


def db_tldr(c):
    paras = c.brief.get('tldr') or []
    return f"<h2>{e(c.label('tldr'))}</h2>" + ''.join(f"<p>{e(p)}</p>" for p in paras) if paras else ''


def db_decisions(c):
    return d_list(c, 'decisions', c.decisions(), numbered=True)


def db_action_items(c):
    return f"<h2>{e(c.label('action_items'))}</h2>{d_actions(c, c.actions())}" if c.actions() else ''


def db_open_questions(c):
    return d_list(c, 'open_questions', c.brief.get('open_questions') or [])


def db_parked(c):
    return d_list(c, 'parked', c.brief.get('parked') or [])


def db_lists(c):
    return db_open_questions(c) + db_parked(c)


def db_next_meeting(c):
    return d_list(c, 'next_meeting', c.brief.get('next_meeting') or [])


def db_participants(c):
    people = c.attendees()
    return (f"<h2>{e(c.label('participants'))}</h2><ul>" + ''.join(
        f"<li>{e(a['name'])}{(' — ' + e(a['role'])) if a.get('role') else ''}</li>" for a in people) + "</ul>") if people else ''


def db_agenda(c):
    items = c.brief.get('agenda') or []
    return (f"<h2>{e(c.label('agenda'))}</h2><ol>" + ''.join(f"<li>{e(a['title'])}</li>" for a in items) + "</ol>") if items else ''


def db_agenda_details(c):
    items = c.brief.get('agenda') or []
    if not items:
        return ''
    out = [f"<h2>{e(c.label('agenda_details'))}</h2>"]
    for n, a in enumerate(items, 1):
        out.append(f"<h3>{n}. {e(a['title'])}</h3>")
        if a.get('discussion'):
            out.append(f"<p><b>{e(c.label('agenda_discussion'))}</b></p><ul>" + ''.join(f"<li>{e(x)}</li>" for x in a['discussion']) + "</ul>")
        if a.get('decisions'):
            out.append(f"<p><b>{e(c.label('agenda_decisions'))}</b></p><ul>" + ''.join(f"<li>{e(d['text'])}</li>" for d in a['decisions']) + "</ul>")
        if a.get('action_items'):
            out.append(f"<p><b>{e(c.label('agenda_actions'))}</b></p><ul>" + ''.join(
                f"<li>{e(x['task'])} — <b>{e(x.get('owner') or 'Owner not set')}</b>{(' — ' + e(x['due'])) if x.get('due') else ''}</li>"
                for x in a['action_items']) + "</ul>")
    return ''.join(out)


def db_speakers(c):
    out = [f"<h2>{e(c.label('speakers'))}</h2>"]
    top = max(s['share'] for s in c.stats) or 1
    out += [f"<p><b style='color:{s['colour']}'>{e(s['name'])}</b>&nbsp; {d_bar(round(28 * s['share'] / top), s['colour'])} "
            f"<span {GREY}>{round(s['share'] * 100)}% · {c.stamp(s['seconds'])} · {s['turns']} turns</span></p>" for s in c.stats]
    size, rows = c.buckets()
    peak = max((sum(r.values()) for r in rows), default=1) or 1
    out.append(f"<h3>Over the meeting</h3><p {GREY}>Each line is {('one minute' if size == 60 else f'{size // 60} minutes')}; the bar shows who held the floor.</p>")
    for i, r in enumerate(rows):
        bars = ''.join(d_bar(round(24 * r[p['id']] / peak), p['colour']) for p in c.people)
        out.append(f"<p style='margin:0;font-family:Consolas,monospace'><span {GREY}>{c.stamp(i * size)}</span> {bars}</p>")
    out.append("<p>" + ' &nbsp; '.join(f"<span style='color:{p['colour']}'>■</span> {e(p['name'])}" for p in c.people) + "</p>")
    if any(s['role'] for s in c.stats):
        out.append(f"<table {TABLE}><tr><th>Speaker</th><th>Role in this meeting</th></tr>"
                   + ''.join(f"<tr><td>{e(s['name'])}</td><td>{e(s['role'])}</td></tr>" for s in c.stats) + "</table>")
    return ''.join(out)


def db_topics(c):
    if not c.topics:
        return ''
    out = [f"<h2>{e(c.label('topics'))}</h2>"]
    for t in c.topics:
        out.append(f"<h3>{c.stamp(t.get('start'))} · {e(t['title'])}</h3>")
        if t.get('lead'):
            out.append(f"<p><i>{e(t['lead'])}</i></p>")
        if t.get('points'):
            out.append("<ul>" + ''.join(f"<li>{e(p)}</li>" for p in t['points']) + "</ul>")
        out += [f"<p style='margin-left:24px;color:#4b5563'>“{e(q['text'])}” <i>({e(q.get('who') or '')}, {c.stamp(q.get('at'))})</i></p>"
                for q in t.get('quotes') or []]
    return ''.join(out)


def db_sections(c):
    out = []
    for s in c.brief.get('sections') or []:
        out.append(f"<h2>{e(s['title'])}</h2>" + ''.join(f"<p>{e(p)}</p>" for p in s.get('text') or []))
        if s.get('items'):
            out.append("<ul>" + ''.join(f"<li>{e(x)}</li>" for x in s['items']) + "</ul>")
    return ''.join(out)


def db_notes(c):
    notes = c.brief.get('notes') or []
    return f"<p {GREY}><i>{e(c.label('notes'))}: {e('; '.join(notes))}</i></p>" if notes else ''


def db_transcript(c):
    turn_dir = " dir='rtl'" if c.turn_dir == 'rtl' else ''
    out = [f"<h1>{e(c.label('transcript'))}</h1>", f"<p {GREY}>{len(c.tr['turns'])} turns · {c.tr.get('words', 0)} words</p>"]
    ti = 0
    for t in c.tr['turns']:
        while ti < len(c.topics) and (c.topics[ti].get('start') or 0) <= t['start']:
            out.append(f"<h3>{e(c.topics[ti]['title'])}</h3>")
            ti += 1
        p = c.by_id[t['speaker']]
        out.append(f"<p{turn_dir}><span {GREY}>[{c.stamp(t['start'])}]</span> <b style='color:{p['colour']}'>{e(p['name'])}:</b> {e(t['text'])}</p>")
    return ''.join(out)


def gdoc_html(c: Ctx, with_transcript: bool = True) -> str:
    blocks = c.tpl.get('doc_blocks') or [b for b in c.tpl['blocks'] if b not in WEB_ONLY]
    if not with_transcript:
        blocks = [b for b in blocks if b != 'transcript']
    while blocks and blocks[-1] == 'page_break':
        blocks = blocks[:-1]
    body = ''.join(globals()['db_' + b](c) for b in blocks if b not in WEB_ONLY)
    rtl = " dir='rtl'" if c.rtl else ''
    return f"<html><head><meta charset='utf-8'><title>{e(c.title)}</title></head><body{rtl}>{body}</body></html>"


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('brief')
    ap.add_argument('transcript')
    ap.add_argument('--template')
    ap.add_argument('--html')
    ap.add_argument('--gdoc')
    ap.add_argument('--no-transcript', action='store_true')
    a = ap.parse_args()
    brief = json.loads(Path(a.brief).read_text(encoding='utf-8'))
    tr = json.loads(Path(a.transcript).read_text(encoding='utf-8'))
    tpl = templates.get(a.template or brief.get('template') or 'standard')
    problems = templates.check(tpl)
    if problems:
        sys.exit('Template problems:\n' + '\n'.join(problems))
    if not (a.html or a.gdoc):
        sys.exit('Give --html and/or --gdoc')
    ctx = Ctx(brief, tr, tpl)
    if a.html:
        Path(a.html).write_text(page_html(ctx), encoding='utf-8')
        print(f"web page ({tpl['id']}) -> {a.html} ({Path(a.html).stat().st_size // 1024} KB)")
    if a.gdoc:
        Path(a.gdoc).write_text(gdoc_html(ctx, not a.no_transcript), encoding='utf-8')
        print(f"Google Doc HTML ({tpl['id']}) -> {a.gdoc} ({Path(a.gdoc).stat().st_size // 1024} KB)")
