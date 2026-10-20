#!/usr/bin/env bash
# Installs, updates or removes Avush skills on macOS and Linux.
#
# One line (install everything for the tools found on this machine):
#   curl -fsSL https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.sh | bash
#
# With options (append after "bash -s --" when piping):
#   --skills meeting-sum          only these skills (comma separated)
#   --targets claude,grok         claude | cursor | grok | agents (comma separated)
#   --update                      same skills, same places, newest version
#   --uninstall                   removes what this script installed
#   --list                        shows the skills in the repo and what is installed
#   --branch main                 another branch
#
# Your own files (for example ~/.claude/meeting-templates) are never touched.
set -euo pipefail

REPO="avibpers/AvushSkills"
BRANCH="main"
SKILLS=""
TARGETS=""
MODE="install"
STATE_DIR="$HOME/.avush-skills"
STATE_FILE="$STATE_DIR/installed.env"

while [ $# -gt 0 ]; do
  case "$1" in
    --skills) SKILLS="$2"; shift 2 ;;
    --targets) TARGETS="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --update) MODE="update"; shift ;;
    --uninstall) MODE="uninstall"; shift ;;
    --list) MODE="list"; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

dir_for() {
  case "$1" in
    claude) echo "$HOME/.claude/skills" ;;
    cursor) echo "$HOME/.cursor/skills" ;;
    grok) echo "$HOME/.grok/skills" ;;
    agents) echo "$HOME/.agents/skills" ;;
    *) echo "Unknown target '$1'. Use: claude, cursor, grok, agents" >&2; exit 1 ;;
  esac
}

# The tools found here. Cursor also reads ~/.claude/skills, so it is only a
# default target when Claude Code isn't installed (no duplicate skills).
find_targets() {
  local found=""
  [ -d "$HOME/.claude" ] && found="claude"
  if [ -d "$HOME/.cursor" ] && [ -z "$found" ]; then found="cursor"; fi
  [ -d "$HOME/.grok" ] && found="${found:+$found,}grok"
  echo "${found:-claude}"
}

# The repo's files: this folder when run from a clone, else a fresh download.
SRC=""; COMMIT=""; TMP=""
get_source() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"
  if [ -n "$here" ] && [ -d "$here/skills" ] && [ "$MODE" != "update" ]; then
    SRC="$here"; COMMIT="$(git -C "$here" rev-parse --short HEAD 2>/dev/null || echo "")"
    return
  fi
  TMP="$(mktemp -d)"
  echo "Downloading $REPO ($BRANCH)..."
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$TMP"
  SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  COMMIT="$(curl -fsSL "https://api.github.com/repos/$REPO/commits/$BRANCH" 2>/dev/null | sed -n 's/.*"sha": "\([0-9a-f]\{7\}\).*/\1/p' | head -n 1 || true)"
}
cleanup() { [ -n "$TMP" ] && rm -rf "$TMP"; }
trap cleanup EXIT

[ -f "$STATE_FILE" ] && . "$STATE_FILE" || true   # sets SAVED_SKILLS, SAVED_TARGETS, SAVED_COMMIT

if [ "$MODE" = "list" ]; then
  get_source
  echo "Skills in the repo:"; ls -1 "$SRC/skills" | sed 's/^/  /'
  if [ -n "${SAVED_SKILLS:-}" ]; then echo "Installed: $SAVED_SKILLS -> $SAVED_TARGETS (commit ${SAVED_COMMIT:-?})"; else echo "Nothing installed by this script yet."; fi
  exit 0
fi

if [ "$MODE" = "uninstall" ]; then
  SKILLS="${SKILLS:-${SAVED_SKILLS:-}}"
  TARGETS="${TARGETS:-${SAVED_TARGETS:-claude,cursor,grok,agents}}"
  for t in ${TARGETS//,/ }; do
    for s in ${SKILLS//,/ }; do
      d="$(dir_for "$t")/$s"
      [ -d "$d" ] && rm -rf "$d" && echo "Removed $s from $t ($d)"
    done
  done
  rm -f "$STATE_FILE"
  echo "Done. Your own templates and files were kept."
  exit 0
fi

if [ "$MODE" = "update" ]; then
  SKILLS="${SKILLS:-${SAVED_SKILLS:-}}"
  TARGETS="${TARGETS:-${SAVED_TARGETS:-}}"
fi
TARGETS="${TARGETS:-$(find_targets)}"

get_source
AVAILABLE="$(ls -1 "$SRC/skills" | tr '\n' ',' | sed 's/,$//')"
SKILLS="${SKILLS:-$AVAILABLE}"
for s in ${SKILLS//,/ }; do
  [ -d "$SRC/skills/$s" ] || { echo "No skill '$s'. Available: $AVAILABLE" >&2; exit 1; }
done

for t in ${TARGETS//,/ }; do
  base="$(dir_for "$t")"; mkdir -p "$base"
  for s in ${SKILLS//,/ }; do
    rm -rf "${base:?}/$s"
    cp -R "$SRC/skills/$s" "$base/$s"
    find "$base/$s" -name __pycache__ -type d -prune -exec rm -rf {} +
    echo "Installed $s for $t -> $base/$s"
  done
done

# Remember everything installed so far, so --update and --uninstall cover all of it.
merge() { printf '%s,%s' "$1" "$2" | tr ',' '\n' | awk 'NF && !seen[$0]++' | paste -sd, -; }
SKILLS="$(merge "${SAVED_SKILLS:-}" "$SKILLS")"
TARGETS="$(merge "${SAVED_TARGETS:-}" "$TARGETS")"
mkdir -p "$STATE_DIR"
printf 'SAVED_SKILLS="%s"\nSAVED_TARGETS="%s"\nSAVED_COMMIT="%s"\n' "$SKILLS" "$TARGETS" "$COMMIT" > "$STATE_FILE"
echo
echo "Done (${COMMIT:-local}). Restart the app or start a new chat to load the skills."
echo "Update later with:  curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash -s -- --update"
