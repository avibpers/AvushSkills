"""Builds one upload-ready zip per skill in dist/: <skill>.zip with a single
top-level folder named after the skill (what claude.ai, ChatGPT and Grok expect).

  python tools/package.py              all skills
  python tools/package.py meeting-sum  one skill
"""
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {'__pycache__', '.git'}
ALLOWED_KEYS = {'name', 'description', 'license', 'allowed-tools', 'metadata', 'compatibility'}


def check(skill: Path) -> None:
    # claude.ai rejects a SKILL.md with other header keys, or a name that isn't the folder's.
    text = (skill / 'SKILL.md').read_text(encoding='utf-8')
    head = re.match(r'^---\n(.*?)\n---', text, re.S)
    if not head:
        sys.exit(f'{skill.name}: SKILL.md has no YAML header')
    keys = {line.split(':', 1)[0].strip() for line in head.group(1).splitlines() if re.match(r'^[a-z-]+:', line)}
    if keys - ALLOWED_KEYS:
        sys.exit(f'{skill.name}: header keys not allowed for upload: {", ".join(sorted(keys - ALLOWED_KEYS))}')
    name = re.search(r'^name:\s*(\S+)', head.group(1), re.M)
    if not name or name.group(1) != skill.name:
        sys.exit(f'{skill.name}: "name" in SKILL.md must equal the folder name')


def build(skill: Path, dist: Path) -> Path:
    check(skill)
    out = dist / f'{skill.name}.zip'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(skill.rglob('*')):
            if f.is_file() and not SKIP_DIRS.intersection(f.parts) and f.suffix != '.pyc':
                z.write(f, Path(skill.name) / f.relative_to(skill))
    return out


if __name__ == '__main__':
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    names = sys.argv[1:] or [p.name for p in sorted((ROOT / 'skills').iterdir()) if p.is_dir()]
    for n in names:
        out = build(ROOT / 'skills' / n, dist)
        print(f'{out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)')
