"""Turns any meeting transcript into one plain JSON shape the summary is written from.

Reads Koli meeting JSON, other JSON with turns or segments, WebVTT / SRT
subtitles, Google Meet caption exports (whose lines grow word by word and
repeat) and plain "Name: text" or "[00:01:02] Name: text" lines.

Usage: python normalize.py <transcript file> [-o out.json]
Output: {"title", "date", "source", "timing", "speakers": [{"id","name"}],
         "turns": [{"speaker","start","end","text"}], "words", "duration_s"}
timing is "real" when the source had times and "estimated" when they were
worked out from word counts (about 130 spoken words a minute).
"""
import json
import re
import sys
from pathlib import Path

WORDS_PER_SECOND = 130 / 60


# ── Shared helpers ───────────────────────────────────────────────────────────

def _seconds(stamp: str) -> float:
    # "01:02:03.500", "02:03,5" or "123.4" → seconds.
    stamp = stamp.strip().replace(',', '.')
    total = 0.0
    for part in stamp.split(':'):
        total = total * 60 + float(part)
    return total


def _words(text: str) -> list:
    return re.findall(r"\w+", text.lower())


def _slug(name: str) -> str:
    return re.sub(r'\W+', '-', name.strip().lower()).strip('-') or 'speaker'


def _date_from_name(path: Path):
    m = re.search(r'(\d{4}-\d{2}-\d{2})[T _](\d{2})[-:](\d{2})', path.name)
    if m:
        return f"{m.group(1)}T{m.group(2)}:{m.group(3)}"
    m = re.search(r'(\d{4}-\d{2}-\d{2})', path.name)
    return m.group(1) if m else None


# ── Readers: each returns turns as [{speaker, start, end, text}] ─────────────

def read_json(data):
    # Koli: {"speakers":[{id,name}], "turns":[{speaker,start,end,text}]}.
    # Others: a list of segments, or {"segments"/"utterances"/"transcript": [...]}.
    extras, names = {}, {}
    if isinstance(data, dict):
        for s in data.get('speakers') or []:
            if isinstance(s, dict) and s.get('id'):
                names[s['id']] = s.get('name') or s['id']
        extras = {k: data.get(k) for k in ('title', 'started_at', 'ended_at') if data.get(k)}
        rows = next((data[k] for k in ('turns', 'segments', 'utterances', 'transcript', 'entries')
                     if isinstance(data.get(k), list)), [])
    else:
        rows = data
    turns = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        text = (r.get('text') or r.get('content') or r.get('transcript') or '').strip()
        if not text:
            continue
        who = str(r.get('speaker') or r.get('speaker_name') or r.get('name') or r.get('participant') or 'Speaker')
        start = r.get('start', r.get('start_time', r.get('startTime')))
        end = r.get('end', r.get('end_time', r.get('endTime')))
        if isinstance(start, str):
            start = _seconds(start)
        if isinstance(end, str):
            end = _seconds(end)
        turns.append({'speaker': who, 'start': start, 'end': end, 'text': text})
    return turns, names, extras


def read_subtitles(text: str):
    # WebVTT or SRT: a cue time line, then text; "<v Name>" or "Name: " gives the speaker.
    turns = []
    for block in re.split(r'\n\s*\n', text.replace('\r', '')):
        lines = [line for line in block.split('\n') if line.strip()]
        for i, line in enumerate(lines):
            m = re.match(r'\s*([\d:.,]+)\s*-->\s*([\d:.,]+)', line)
            if not m:
                continue
            body, who = ' '.join(lines[i + 1:]), 'Speaker'
            v = re.match(r'<v\s+([^>]+)>(.*)', body)
            n = re.match(r'([^:]{1,40}):\s+(.*)', body)
            if v:
                who, body = v.group(1), v.group(2)
            elif n:
                who, body = n.group(1), n.group(2)
            body = re.sub(r'</?[^>]+>', '', body).strip()
            if body:
                turns.append({'speaker': who.strip(), 'start': _seconds(m.group(1)),
                              'end': _seconds(m.group(2)), 'text': body})
            break
    return turns


LINE = re.compile(r'^\s*(?:\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-–]?\s*)?'
                  r'([^:(){}\[\]<>"\']{1,40}?)\s*:\s+(.+)$')


def read_lines(text: str):
    # "Name: text" lines, optionally with a time in front. Names seen only once
    # or twice are page junk (Meet exports start with UI text), not speakers.
    rows = []
    for raw in text.replace('\r', '').split('\n'):
        m = LINE.match(raw)
        if m:
            rows.append((m.group(1), m.group(2).strip(), m.group(3).strip()))
    counts = {}
    for _, who, _ in rows:
        counts[who] = counts.get(who, 0) + 1
    rows = [r for r in rows if counts[r[1]] >= 3 and r[1].lower() not in ('unknown', 'http', 'https')]
    if any(r[0] for r in rows):
        return [{'speaker': who, 'start': _seconds(t) if t else None, 'end': None, 'text': body}
                for t, who, body in rows]
    return merge_rolling([(who, body) for _, who, body in rows])


# ── Google Meet rolling captions ─────────────────────────────────────────────
# Meet writes a speaker's caption again every time it grows, sometimes fixing
# earlier words, and later re-prints old pieces. Keep the last version of each
# growing caption and drop the re-prints.

def _same_caption(old: list, new: list) -> bool:
    if not old or not new:
        return False
    # The old caption may end mid-word: "והפ" grows into "והפעלת תרגום".
    if len(old) <= len(new) and old[:-1] == new[:len(old) - 1] and new[len(old) - 1].startswith(old[-1]):
        return True
    k = min(len(old), len(new), 6)
    if old[:k] == new[:k]:
        return True
    # A fix near the start: most of the old words still lead the new line.
    k = min(len(old), len(new))
    same = sum(1 for a, b in zip(old[:k], new[:k]) if a == b)
    return k >= 4 and same / k >= 0.6


def _reprint(words: list, done: list) -> bool:
    # True when these words already sit inside an earlier caption of the speaker.
    probe = words[:min(len(words), 8)]
    n = len(probe)
    for prev in done:
        for i in range(0, len(prev) - n + 1):
            if prev[i:i + n] == probe:
                return len(words) <= len(prev) - i + 3
    return False


def merge_rolling(rows):
    current = {}      # speaker -> [order, words, text]
    finished = []     # [order, speaker, words, text]
    order = 0
    for who, text in rows:
        words = _words(text)
        if not words or words == _words(who):
            continue  # Meet sometimes prints just the name
        cur = current.get(who)
        if cur and _same_caption(cur[1], words):
            if len(words) >= len(cur[1]) - 2:
                cur[1], cur[2] = words, text
            continue
        # A caption can keep growing after a short fragment interrupted it:
        # grow that recent caption in place instead of starting a copy.
        recent = [f for f in finished if f[1] == who][-4:]
        grown = next((f for f in reversed(recent) if _same_caption(f[2], words)), None)
        if grown:
            if len(words) >= len(grown[2]):
                grown[2], grown[3] = words, text
            continue
        done = [f[2] for f in finished if f[1] == who] + ([cur[1]] if cur else [])
        if _reprint(words, done):
            continue
        if cur:
            finished.append([cur[0], who, cur[1], cur[2]])
        current[who] = [order, words, text]
        order += 1
    for who, cur in current.items():
        finished.append([cur[0], who, cur[1], cur[2]])
    finished.sort(key=lambda f: f[0])
    return [{'speaker': f[1], 'start': None, 'end': None, 'text': f[3]} for f in finished]


# ── Times and output ─────────────────────────────────────────────────────────

def fill_times(turns) -> str:
    # Missing times are estimated from word counts so the charts still work.
    real = all(t.get('start') is not None for t in turns)
    clock = 0.0
    for t in turns:
        n = max(len(_words(t['text'])), 1)
        if real:
            if t.get('end') is None:
                t['end'] = t['start'] + n / WORDS_PER_SECOND
        else:
            t['start'] = clock
            clock += n / WORDS_PER_SECOND
            t['end'] = clock
    return 'real' if real else 'estimated'


def normalize(path: Path) -> dict:
    raw = path.read_text(encoding='utf-8-sig', errors='replace')
    names, extras = {}, {}
    turns = []
    if path.suffix.lower() == '.json' or raw.lstrip()[:1] in ('[', '{'):
        try:
            turns, names, extras = read_json(json.loads(raw))
        except ValueError:
            turns = read_lines(raw)
    elif '-->' in raw:
        turns = read_subtitles(raw)
    else:
        turns = read_lines(raw)
    if not turns:
        raise SystemExit('No speaker turns found. Read the file yourself and build the turns by hand.')
    timing = fill_times(turns)
    turns.sort(key=lambda t: t['start'])

    # Speaker ids are stable slugs; names stay as the transcript wrote them.
    ids, speakers = {}, []
    for t in turns:
        key = t['speaker']
        if key not in ids:
            ids[key] = key if key in names else _slug(key)
            speakers.append({'id': ids[key], 'name': names.get(key, key)})
        t['speaker'] = ids[key]
        t['start'], t['end'] = round(t['start'], 1), round(t['end'], 1)
    return {
        'title': extras.get('title') or path.stem,
        'date': extras.get('started_at') or _date_from_name(path),
        'source': str(path),
        'timing': timing,
        'speakers': speakers,
        'turns': turns,
        'words': sum(len(_words(t['text'])) for t in turns),
        'duration_s': round(max(t['end'] for t in turns) - min(t['start'] for t in turns)),
    }


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    out = None
    if '-o' in args:
        i = args.index('-o')
        out = args[i + 1]
        args = args[:i] + args[i + 2:]
    result = normalize(Path(args[0]))
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if out:
        Path(out).write_text(text, encoding='utf-8')
        print(f"{len(result['turns'])} turns, {len(result['speakers'])} speakers, "
              f"{result['words']} words, timing {result['timing']} -> {out}")
    else:
        sys.stdout.reconfigure(encoding='utf-8')
        print(text)
