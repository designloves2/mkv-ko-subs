#!/bin/bash
# mkv-ko-subs 스킬 설치: ~/.claude/skills/mkv-ko-subs 로 복사
set -e
DEST="$HOME/.claude/skills/mkv-ko-subs"
SRC="$(cd "$(dirname "$0")" && pwd)"
for c in mkvmerge mkvextract ffmpeg python3; do
  command -v $c >/dev/null || echo "경고: '$c' 가 없습니다. (macOS: brew install mkvtoolnix ffmpeg)"
done
mkdir -p "$DEST/scripts"
cp "$SRC/SKILL.md" "$DEST/SKILL.md"
cp "$SRC/scripts/mkv_subs.py" "$DEST/scripts/mkv_subs.py"
chmod +x "$DEST/scripts/mkv_subs.py"
echo "설치 완료: $DEST (Claude Code를 새 세션으로 시작하면 /mkv-ko-subs 로 사용 가능)"
